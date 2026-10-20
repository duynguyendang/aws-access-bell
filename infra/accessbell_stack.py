from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_cognito as cognito,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_events as events,
    aws_iam as iam,
    aws_logs as logs,
    aws_rds as rds,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct
import os
from pathlib import Path


class AccessBellStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(
            self,
            "AccessBellVpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        db_secret = secretsmanager.Secret(
            self,
            "AccessBellDbSecret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "accessbell"}',
                generate_string_key="password",
                exclude_punctuation=True,
            ),
        )

        def _token_secret(ident: str) -> secretsmanager.Secret:
            return secretsmanager.Secret(
                self,
                ident,
                generate_secret_string=secretsmanager.SecretStringGenerator(
                    secret_string_template="{}",
                    generate_string_key="token",
                    exclude_punctuation=True,
                ),
            )

        api_token_secret = _token_secret("AccessBellApiToken")
        mcp_token_secret = _token_secret("AccessBellMcpToken")
        webhook_secret = _token_secret("AccessBellRingWebhookSecret")

        db_security_group = ec2.SecurityGroup(
            self,
            "DbSecurityGroup",
            vpc=vpc,
            description="AccessBell RDS Postgres SG",
            allow_all_outbound=True,
        )

        db = rds.DatabaseInstance(
            self,
            "AccessBellPostgres",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16_4
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[db_security_group],
            database_name="accessbell",
            credentials=rds.Credentials.from_secret(db_secret),
            allocated_storage=20,
            max_allocated_storage=50,
            storage_encrypted=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_minor_version_upgrade=True,
        )

        user_pool = cognito.UserPool(
            self,
            "AccessBellUserPool",
            user_pool_name="accessbell-pool",
            self_sign_up_enabled=False,
            removal_policy=RemovalPolicy.DESTROY,
        )

        scope_service = cognito.ResourceServerScope(
            scope_name="mcp:service",
            scope_description="Service discovery and ping only",
        )
        scope_tools = cognito.ResourceServerScope(
            scope_name="mcp:tools",
            scope_description="Execute AccessBell MCP tools",
        )
        scope_resources = cognito.ResourceServerScope(
            scope_name="mcp:resources",
            scope_description="Read AccessBell MCP resources",
        )
        resource_server = user_pool.add_resource_server(
            "AccessBellResourceServer",
            identifier="accessbell",
            scopes=[scope_service, scope_tools, scope_resources],
        )

        callback_urls = self.node.try_get_context("alexa_callback_urls")
        if isinstance(callback_urls, str):
            callback_urls = [callback_urls]

        service_client = user_pool.add_client(
            "ServiceMcpClient",
            user_pool_client_name="accessbell-service",
            generate_secret=True,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(client_credentials=True),
                scopes=[
                    cognito.OAuthScope.custom("accessbell/mcp:service"),
                ],
            ),
        )
        service_client.node.add_dependency(resource_server)

        alexa_client = None
        if callback_urls:
            alexa_client = user_pool.add_client(
                "AlexaMcpClient",
                user_pool_client_name="alexa-plus-mcp",
                generate_secret=True,
                o_auth=cognito.OAuthSettings(
                    flows=cognito.OAuthFlows(
                        authorization_code_grant=True,
                    ),
                    scopes=[
                        cognito.OAuthScope.custom("accessbell/mcp:tools"),
                        cognito.OAuthScope.custom("accessbell/mcp:resources"),
                    ],
                    callback_urls=callback_urls,
                ),
            )
            alexa_client.node.add_dependency(resource_server)

        oauth_client_ids = [service_client.user_pool_client_id]
        if alexa_client:
            oauth_client_ids.append(alexa_client.user_pool_client_id)

        cluster = ecs.Cluster(self, "AccessBellCluster", vpc=vpc)

        event_bus = events.EventBus(self, "AccessBellEventBus")

        task_role = iam.Role(
            self,
            "AccessBellTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sns:Publish"],
                resources=["*"],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=["*"],
            )
        )
        event_bus.grant_put_events_to(task_role)

        task_def = ecs.FargateTaskDefinition(
            self,
            "AccessBellTaskDef",
            cpu=256,
            memory_limit_mib=512,
            task_role=task_role,
        )

        repo_root = str(Path(__file__).resolve().parents[1])
        llm_provider = os.getenv("LLM_PROVIDER", "bedrock")
        llm_key_env = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
        }.get(llm_provider)
        llm_default_model = {
            "bedrock": "us.amazon.nova-2-lite-v1:0",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku-latest",
            "google": "gemini-2.0-flash",
        }.get(llm_provider, "us.amazon.nova-2-lite-v1:0")
        container_image = ecs.ContainerImage.from_asset(
            repo_root,
            file="Dockerfile",
            build_args={
                "INSTALL_LLM": "true" if llm_provider in {"openai", "anthropic", "google", "ollama"} else "false",
            },
        )

        log_group = logs.LogGroup(
            self,
            "AccessBellLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        db_host = db.db_instance_endpoint_address
        db_port = db.db_instance_endpoint_port
        jwks_url = f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}/.well-known/jwks.json"
        issuer_url = f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}"

        container_secrets = {
            "POSTGRES_PASSWORD": ecs.Secret.from_secrets_manager(
                db_secret, "password"
            ),
            "API_TOKEN": ecs.Secret.from_secrets_manager(api_token_secret, "token"),
            "MCP_HTTP_TOKEN": ecs.Secret.from_secrets_manager(mcp_token_secret, "token"),
            "RING_WEBHOOK_SECRET": ecs.Secret.from_secrets_manager(webhook_secret, "token"),
        }
        llm_key_secret_name = os.getenv("LLM_API_KEY_SECRET_NAME", "")
        if llm_key_secret_name and llm_key_env:
            llm_key_secret = secretsmanager.Secret.from_secret_name_v2(
                self, "AccessBellLlmApiKey", llm_key_secret_name
            )
            container_secrets[llm_key_env] = ecs.Secret.from_secrets_manager(
                llm_key_secret
            )

        container = task_def.add_container(
            "AccessBellContainer",
            image=container_image,
            environment={
                "PORT": "8080",
                "APP_ENV": "production",
                "POSTGRES_HOST": db_host,
                "POSTGRES_PORT": str(db_port),
                "POSTGRES_USER": "accessbell",
                "POSTGRES_DB": "accessbell",
                "API_AUTH_DISABLED": "false",
                "RING_WEBHOOK_ENABLED": "true",
                "LLM_PROVIDER": llm_provider,
                "LLM_MODEL": os.getenv("LLM_MODEL", llm_default_model),
                "RATE_LIMIT_PER_MINUTE": os.getenv("RATE_LIMIT_PER_MINUTE", "50"),
                "NOTIFIER_PROVIDER": "sns",
                "FORWARDED_ALLOW_IPS": vpc.vpc_cidr_block,
                "EVENTBRIDGE_BUS_NAME": event_bus.event_bus_name,
                "OAUTH_JWKS_URL": jwks_url,
                "OAUTH_ISSUER": issuer_url,
                "OAUTH_CLIENT_IDS": ",".join(oauth_client_ids),
                "OAUTH_SCOPE_PREFIX": "accessbell/",
                "MCP_ORIGIN": "https://alexa.amazon.com,https://developer.amazon.com",
            },
            secrets=container_secrets,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="accessbell",
                log_group=log_group,
            ),
        )
        container.add_port_mappings(
            ecs.PortMapping(container_port=8080, protocol=ecs.Protocol.TCP)
        )

        ecs_security_group = ec2.SecurityGroup(
            self,
            "EcsSecurityGroup",
            vpc=vpc,
            description="AccessBell ECS Task SG",
            allow_all_outbound=True,
        )
        db_security_group.add_ingress_rule(
            peer=ecs_security_group,
            connection=ec2.Port.tcp(5432),
            description="PostgreSQL access from ECS tasks",
        )

        fargate_service = ecs.FargateService(
            self,
            "AccessBellFargateService",
            cluster=cluster,
            task_definition=task_def,
            desired_count=1,
            assign_public_ip=True,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[ecs_security_group],
        )

        alb = elbv2.ApplicationLoadBalancer(
            self,
            "AccessBellALB",
            vpc=vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        target_group = elbv2.ApplicationTargetGroup(
            self,
            "AccessBellTargets",
            vpc=vpc,
            port=8080,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[fargate_service],
            health_check=elbv2.HealthCheck(
                path="/health",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
            deregistration_delay=Duration.seconds(30),
        )

        certificate_arn = (
            self.node.try_get_context("certificate_arn")
            or os.getenv("CERTIFICATE_ARN")
        )
        if certificate_arn:
            https_listener = alb.add_listener(
                "HttpsListener",
                port=443,
                open=True,
                certificates=[elbv2.ListenerCertificate.from_arn(certificate_arn)],
            )
            https_listener.add_target_groups(
                "HttpsTargets", target_groups=[target_group]
            )
            alb.add_listener(
                "HttpListener",
                port=80,
                open=True,
                default_action=elbv2.ListenerAction.redirect(
                    protocol="HTTPS",
                    port="443",
                    permanent=True,
                ),
            )
            service_url = f"https://{alb.load_balancer_dns_name}"
        else:
            http_listener = alb.add_listener("HttpListener", port=80, open=True)
            http_listener.add_target_groups(
                "HttpTargets", target_groups=[target_group]
            )
            service_url = f"http://{alb.load_balancer_dns_name}"

        target_group.set_attribute(
            "deregistration_delay.timeout_seconds", "30"
        )
        alb.set_attribute("idle_timeout.timeout_seconds", "300")

        CfnOutput(self, "ALBDnsName", value=alb.load_balancer_dns_name)
        CfnOutput(self, "ServiceUrl", value=service_url)
        CfnOutput(self, "RingWebhookUrl", value=f"{service_url}/webhooks/ring")
        CfnOutput(self, "HttpsEnabled", value="true" if certificate_arn else "false")
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "CognitoClientId", value=service_client.user_pool_client_id)
        CfnOutput(
            self,
            "AlexaClientId",
            value=alexa_client.user_pool_client_id if alexa_client else "not-configured",
        )
        CfnOutput(self, "JwksUrl", value=jwks_url)
        CfnOutput(self, "EventBusName", value=event_bus.event_bus_name)
        CfnOutput(self, "ApiTokenSecretArn", value=api_token_secret.secret_arn)
        CfnOutput(self, "McpTokenSecretArn", value=mcp_token_secret.secret_arn)
        CfnOutput(self, "RingWebhookSecretArn", value=webhook_secret.secret_arn)
