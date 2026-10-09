#!/usr/bin/env python3
import argparse
import json
import socket

parser = argparse.ArgumentParser(description="Send one IDTag push request over the TCP socket")
parser.add_argument("--host", default="211.23.22.158")
parser.add_argument("--port", type=int, default=7002)
parser.add_argument("--secret", required=True)
parser.add_argument("--community", required=True)
parser.add_argument("--card", required=True)
parser.add_argument("--title", required=True)
parser.add_argument("--body", required=True)
args = parser.parse_args()

payload = {
    "secret": args.secret,
    "community_code": args.community,
    "card_number": args.card,
    "title": args.title,
    "body": args.body,
    "data": {},
}
with socket.create_connection((args.host, args.port), timeout=10) as connection:
    connection.sendall(json.dumps(payload, ensure_ascii=False).encode() + b"\n")
    print(connection.makefile().readline().rstrip())
