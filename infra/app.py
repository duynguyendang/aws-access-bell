import os
import aws_cdk as cdk
from accessbell_stack import AccessBellStack

app = cdk.App()
env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT", os.getenv("AWS_ACCOUNT_ID")),
    region=os.getenv("CDK_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-1")),
)

AccessBellStack(app, "AccessBellStack", env=env)
app.synth()
