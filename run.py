import uvicorn

from idtag_push.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("idtag_push.main:app", host=settings.http_host, port=settings.http_port)
