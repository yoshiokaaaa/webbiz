# -*- coding: utf-8 -*-

import os
import time
import redis
import gevent
import json
from flask import Flask, render_template, request
from flask import redirect, url_for
from flask import make_response
from flask_sockets import Sockets

# REDIS_URL = os.environ["REDIS_URL"]
REDIS_CHAN = "chat"

app = Flask(__name__)
app.debug = True

sockets = Sockets(app)
# redis = redis.from_url(REDIS_URL)
redis = redis.Redis()



class ChatBackend(object):


    def __init__(self):
        self.clients = dict()
        self.pubsub = redis.pubsub()
        self.pubsub.subscribe(REDIS_CHAN)


    def __iter_data(self):
        for message in self.pubsub.listen():
            data = message.get("data")
            app.logger.info("data from redis: {}".format(data))
            if message["type"] == "message":
                data = unicode(data, "utf-8")
                app.logger.info(u"Sending message: {}".format(data))
                yield data


    def register(self, client, handle, roomnum):
        self.clients[client] = {
                                "handle":  handle,
                                "roomnum": roomnum,
                                }
        for k,v in self.clients.items():
            print("key:", k, "values:", v)


    def send(self, client, data):
        try:
            d_data = json.loads(data)
            roomnum = d_data.get("roomnum", 0)
            if self.clients[client]["roomnum"] == roomnum:
                data = json.dumps(d_data)
                client.send(data)
        except Exception:
            self.delete_client(client)


    def send_member(self, client):
        while True:
            member = list()
            for v in redis.lrange(client["roomnum"], 0, -1):
                if v["roomnum"]==self.clients[client]["roomnum"]:
                    member.append(v["handle"])
            member_data = json.dumps({"member": member})
            try:
                client.send(member_data)
            except Exception:
                self.delete_client(client)

            gevent.sleep(1)


    def delete_client(self, client):
        del self.clients[client]
        redis.delete(str(client))


    def run(self):
        for data in self.__iter_data():
            for client in self.clients.keys():
                   gevent.spawn(self.send, client, data)
                   gevent.spawn(self.send_member, client)


    def start(self):
        gevent.spawn(self.run)



chats = ChatBackend()
chats.start()


@app.route("/", methods=["GET"])
def login():
    global handle, roomnum
    if (request.args.get("name") and request.args.get("roomnum")):
        handle = request.args.get("name")
        roomnum = str(request.args.get("roomnum"))
        print("login:", handle, roomnum)
        redis.set("handle", handle)
        redis.set("roomnum", roomnum)
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/index")
def index():
    handle = unicode(redis.get("handle"), "utf-8")
    roomnum = unicode(redis.get("roomnum"), "utf-8")
    print("index:", handle, roomnum)
    return render_template("index.html", 
                           handle=handle, 
                           roomnum=roomnum
                           )


@sockets.route("/index/submit")
def inbox(ws):
    while not ws.closed:
        gevent.sleep(0.1)
        message = ws.receive()
        print("data from ws:", message, type(message))

        if message:
            if not message==u"please keep me":
                app.logger.info(u"Inserting message: {}".format(message))
                redis.publish(REDIS_CHAN, message)


@sockets.route("/index/receive")
def outbox(ws):
    handle = unicode(redis.get("handle"), "utf-8")
    roomnum = unicode(redis.get("roomnum"), "utf-8")
    print("regist:", handle, roomnum)
    chats.register(ws, handle, roomnum)
    redis.lpush(roomnum, str(ws), handle)
    app.logger.info(u"regist: {}".format(ws))
    redis.set("handle", "")
    redis.set("roomnum", "")

    while not ws.closed:
        gevent.sleep(0.1)

    if ws.closed:
        chats.delete_client[ws]


def inbox(ws):
    while not ws.closed:
        gevent.sleep(0.1)
