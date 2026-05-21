# -*- coding: utf-8 -*-

from argparse import ArgumentParser

from app import create_app


app = create_app()


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=25601, type=int)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, threaded=True)
