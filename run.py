"""真相捕手 - 启动入口

用法:
    python run.py              # 启动 Gradio Web 界面 (默认)
    python run.py --api        # 启动 FastAPI 后端 (用于前后端分离)
"""

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="真相捕手 TruthCatcher")
    parser.add_argument(
        "--api",
        action="store_true",
        help="启动 FastAPI 后端（默认启动 Gradio 界面）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="服务端口（默认7860）",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="监听地址（默认0.0.0.0）",
    )
    args = parser.parse_args()

    if args.api:
        import uvicorn
        logger.info(f"启动 FastAPI 服务: http://{args.host}:{args.port}")
        logger.info(f"API文档: http://{args.host}:{args.port}/docs")
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            log_level="info",
        )
    else:
        # 启动 Gradio UI
        from app.ui.gradio_app import main as gradio_main
        from app.config import settings
        settings.app_host = args.host
        settings.app_port = args.port
        logger.info(f"启动 Gradio 界面: http://{args.host}:{args.port}")
        gradio_main()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    main()
