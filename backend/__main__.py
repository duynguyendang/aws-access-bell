import uvicorn

from .config import settings


def main():
    uvicorn.run("backend.main:app", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()