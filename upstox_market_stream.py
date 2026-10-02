from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from copy import deepcopy
from typing import Any

import requests
import websockets.sync.client
from google.protobuf import descriptor_pb2, descriptor_pool, message
from google.protobuf.wrappers_pb2 import DoubleValue

from config import (
    UPSTOX_ACCESS_TOKEN,
    UPSTOX_API_BASE_URL,
    UPSTOX_REQUEST_TIMEOUT_SECONDS,
    UPSTOX_WS_MAX_INSTRUMENTS,
    UPSTOX_WS_RECONNECT_SECONDS,
)


# A small runtime-generated descriptor keeps the project independent of protoc
# while remaining wire-compatible with Upstox Market Data Feed V3.
def _build_feed_message():
    fd = descriptor_pb2.FileDescriptorProto()
    fd.name = "MarketDataFeedV3.proto"
    fd.package = "com.upstox.marketdatafeederv3udapi.rpc.proto"
    fd.syntax = "proto3"
    fd.dependency.append("google/protobuf/wrappers.proto")

    def field(msg, name, number, typ, label=1, type_name=None, oneof_index=None):
        f = msg.field.add(); f.name=name; f.number=number; f.type=typ; f.label=label
        if type_name: f.type_name=type_name
        if oneof_index is not None: f.oneof_index=oneof_index
        return f

    TYPE = descriptor_pb2.FieldDescriptorProto
    for name, fields in {
        "LTPC": [("ltp",1,TYPE.TYPE_DOUBLE),("ltt",2,TYPE.TYPE_INT64),("ltq",3,TYPE.TYPE_INT64),("cp",4,TYPE.TYPE_DOUBLE)],
        "Quote": [("bidQ",1,TYPE.TYPE_INT64),("bidP",2,TYPE.TYPE_DOUBLE),("askQ",3,TYPE.TYPE_INT64),("askP",4,TYPE.TYPE_DOUBLE)],
        "OptionGreeks": [("delta",1,TYPE.TYPE_DOUBLE),("theta",2,TYPE.TYPE_DOUBLE),("gamma",3,TYPE.TYPE_DOUBLE),("vega",4,TYPE.TYPE_DOUBLE),("rho",5,TYPE.TYPE_DOUBLE)],
        "OHLC": [("interval",1,TYPE.TYPE_STRING),("open",2,TYPE.TYPE_DOUBLE),("high",3,TYPE.TYPE_DOUBLE),("low",4,TYPE.TYPE_DOUBLE),("close",5,TYPE.TYPE_DOUBLE),("vol",6,TYPE.TYPE_INT64),("ts",7,TYPE.TYPE_INT64)],
    }.items():
        m=fd.message_type.add(); m.name=name
        for item in fields: field(m,*item)
    m=fd.message_type.add(); m.name="MarketLevel"; field(m,"bidAskQuote",1,TYPE.TYPE_MESSAGE,3,".com.upstox.marketdatafeederv3udapi.rpc.proto.Quote")
    m=fd.message_type.add(); m.name="MarketOHLC"; field(m,"ohlc",1,TYPE.TYPE_MESSAGE,3,".com.upstox.marketdatafeederv3udapi.rpc.proto.OHLC")
    m=fd.message_type.add(); m.name="MarketFullFeed"
    for name,num,tn in [("ltpc",1,"LTPC"),("marketLevel",2,"MarketLevel"),("optionGreeks",3,"OptionGreeks"),("marketOHLC",4,"MarketOHLC")]: field(m,name,num,TYPE.TYPE_MESSAGE,1,".com.upstox.marketdatafeederv3udapi.rpc.proto."+tn)
    for name,num,typ in [("atp",5,TYPE.TYPE_DOUBLE),("vtt",6,TYPE.TYPE_INT64),("oi",7,TYPE.TYPE_DOUBLE),("iv",8,TYPE.TYPE_DOUBLE),("tbq",9,TYPE.TYPE_DOUBLE),("tsq",10,TYPE.TYPE_DOUBLE),("iep",11,TYPE.TYPE_DOUBLE),("rp",12,TYPE.TYPE_DOUBLE),("ieq",13,TYPE.TYPE_INT64),("iiqTotal",14,TYPE.TYPE_INT64),("iiqM",15,TYPE.TYPE_INT64),("casEligible",16,TYPE.TYPE_BOOL)]: field(m,name,num,typ)
    m=fd.message_type.add(); m.name="IndexFullFeed"
    field(m,"ltpc",1,TYPE.TYPE_MESSAGE,1,".com.upstox.marketdatafeederv3udapi.rpc.proto.LTPC"); field(m,"marketOHLC",2,TYPE.TYPE_MESSAGE,1,".com.upstox.marketdatafeederv3udapi.rpc.proto.MarketOHLC")
    m=fd.message_type.add(); m.name="FullFeed"; m.oneof_decl.add().name="FullFeedUnion"
    field(m,"marketFF",1,TYPE.TYPE_MESSAGE,1,".com.upstox.marketdatafeederv3udapi.rpc.proto.MarketFullFeed",0); field(m,"indexFF",2,TYPE.TYPE_MESSAGE,1,".com.upstox.marketdatafeederv3udapi.rpc.proto.IndexFullFeed",0)
    m=fd.message_type.add(); m.name="FirstLevelWithGreeks"
    field(m,"ltpc",1,TYPE.TYPE_MESSAGE,1,".com.upstox.marketdatafeederv3udapi.rpc.proto.LTPC"); field(m,"firstDepth",2,TYPE.TYPE_MESSAGE,1,".com.upstox.marketdatafeederv3udapi.rpc.proto.Quote"); field(m,"optionGreeks",3,TYPE.TYPE_MESSAGE,1,".com.upstox.marketdatafeederv3udapi.rpc.proto.OptionGreeks"); field(m,"vtt",4,TYPE.TYPE_INT64); field(m,"oi",5,TYPE.TYPE_DOUBLE); field(m,"iv",6,TYPE.TYPE_DOUBLE)
    enum=m=fd.enum_type.add(); enum.name="RequestMode"
    for n,v in [("ltpc",0),("full_d5",1),("option_greeks",2),("full_d30",3)]: x=enum.value.add(); x.name=n; x.number=v
    enum=fd.enum_type.add(); enum.name="Type"
    for n,v in [("initial_feed",0),("live_feed",1),("market_info",2)]: x=enum.value.add(); x.name=n; x.number=v
    enum=fd.enum_type.add(); enum.name="MarketStatus"
    for n,v in [("PRE_OPEN_START",0),("PRE_OPEN_END",1),("NORMAL_OPEN",2),("NORMAL_CLOSE",3),("CLOSING_START",4),("CLOSING_END",5)]: x=enum.value.add(); x.name=n; x.number=v
    m=fd.message_type.add(); m.name="Feed"; m.oneof_decl.add().name="FeedUnion"
    field(m,"ltpc",1,TYPE.TYPE_MESSAGE,1,".com.upstox.marketdatafeederv3udapi.rpc.proto.LTPC",0); field(m,"fullFeed",2,TYPE.TYPE_MESSAGE,1,".com.upstox.marketdatafeederv3udapi.rpc.proto.FullFeed",0); field(m,"firstLevelWithGreeks",3,TYPE.TYPE_MESSAGE,1,".com.upstox.marketdatafeederv3udapi.rpc.proto.FirstLevelWithGreeks",0); field(m,"requestMode",4,TYPE.TYPE_ENUM,1,".com.upstox.marketdatafeederv3udapi.rpc.proto.RequestMode")
    m=fd.message_type.add(); m.name="FeedResponse"; field(m,"type",1,TYPE.TYPE_ENUM,1,".com.upstox.marketdatafeederv3udapi.rpc.proto.Type")
    entry=m.nested_type.add(); entry.name="FeedsEntry"; entry.options.map_entry=True; field(entry,"key",1,TYPE.TYPE_STRING); field(entry,"value",2,TYPE.TYPE_MESSAGE,1,".com.upstox.marketdatafeederv3udapi.rpc.proto.Feed")
    field(m,"feeds",2,TYPE.TYPE_MESSAGE,3,".com.upstox.marketdatafeederv3udapi.rpc.proto.FeedResponse.FeedsEntry"); field(m,"currentTs",3,TYPE.TYPE_INT64)
    pool=descriptor_pool.Default(); desc=pool.Add(fd); return message.Message

_FEED_RESPONSE = None

def _feed_response_class():
    global _FEED_RESPONSE
    if _FEED_RESPONSE is None:
        _build_feed_message()
        _FEED_RESPONSE = message.Message
        # DynamicMessage class factory is exposed through GetMessageClass.
        from google.protobuf.message_factory import GetMessageClass
        _FEED_RESPONSE = GetMessageClass(descriptor_pool.Default().FindMessageTypeByName("com.upstox.marketdatafeederv3udapi.rpc.proto.FeedResponse"))
    return _FEED_RESPONSE


class UpstoxMarketStream:
    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = (access_token or UPSTOX_ACCESS_TOKEN).strip()
        self._lock = threading.RLock()
        self._instruments: set[str] = set()
        self._data: dict[str, dict[str, Any]] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._ws = None
        self.connected = False
        self.last_error = ""
        self.last_message_at = 0.0

    def set_instruments(self, instruments: list[str]) -> None:
        clean = {x.strip() for x in instruments if x and x.strip()}
        if len(clean) > UPSTOX_WS_MAX_INSTRUMENTS:
            clean = set(sorted(clean)[:UPSTOX_WS_MAX_INSTRUMENTS])
        with self._lock:
            old = set(self._instruments)
            changed = clean != old
            self._instruments = clean
        if changed and self._ws is not None:
            try:
                removed = sorted(old - clean)
                added = sorted(clean - old)
                if removed:
                    self._send_subscription("unsub", removed)
                if added:
                    self._send_subscription("sub", added)
            except Exception:
                self._wake.set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive(): return
        self._stop.clear(); self._thread = threading.Thread(target=self._run, name="upstox-market-stream", daemon=True); self._thread.start()

    def stop(self) -> None:
        self._stop.set(); self._wake.set()
        ws=self._ws
        if ws:
            try: ws.close()
            except Exception: pass

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock: return deepcopy(self._data)

    def _authorize(self) -> str:
        if not self.access_token: raise RuntimeError("UPSTOX_ACCESS_TOKEN is missing.")
        r=requests.get(f"{UPSTOX_API_BASE_URL}/v3/feed/market-data-feed/authorize", headers={"Accept":"application/json","Authorization":f"Bearer {self.access_token}"}, timeout=UPSTOX_REQUEST_TIMEOUT_SECONDS)
        if not r.ok: raise RuntimeError(f"WebSocket authorization failed: HTTP {r.status_code} {r.text[:300]}")
        payload=r.json(); uri=payload.get("data",{}).get("authorized_redirect_uri")
        if not uri: raise RuntimeError("Upstox did not return authorized_redirect_uri.")
        return uri

    def _send_subscription(self, method: str, keys: list[str]) -> None:
        if not self._ws or not keys: return
        payload={"guid":uuid.uuid4().hex,"method":method,"data":{"mode":"full","instrumentKeys":keys}}
        self._ws.send(json.dumps(payload).encode("utf-8"))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                uri=self._authorize()
                with websockets.sync.client.connect(uri, open_timeout=10, close_timeout=2, ping_interval=20, ping_timeout=20, max_size=None) as ws:
                    self._ws=ws; self.connected=True; self.last_error=""
                    with self._lock: keys=list(self._instruments)
                    self._send_subscription("sub", keys)
                    while not self._stop.is_set():
                        try:
                            raw=ws.recv(timeout=2)
                        except TimeoutError:
                            continue
                        if raw is None: continue
                        self._handle(raw); self.last_message_at=time.time()
                        if self._wake.is_set():
                            self._wake.clear()
                            with self._lock: current=list(self._instruments)
                            self._send_subscription("sub", current)
            except Exception as exc:
                self.last_error=str(exc); logging.warning("Upstox websocket: %s", exc)
                time.sleep(UPSTOX_WS_RECONNECT_SECONDS)
            finally:
                self.connected=False; self._ws=None

    def _handle(self, raw: bytes | str) -> None:
        if not isinstance(raw,(bytes,bytearray)): return
        cls=_feed_response_class(); response=cls(); response.ParseFromString(raw)
        for key, feed in response.feeds.items():
            item=self._extract_feed(feed)
            if item:
                with self._lock: self._data[key]=item

    @staticmethod
    def _extract_feed(feed: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if feed.HasField("ltpc"):
            out.update({"ltp":feed.ltpc.ltp,"ltt":feed.ltpc.ltt,"cp":feed.ltpc.cp})
        if feed.HasField("fullFeed"):
            full=feed.fullFeed
            ff=full.marketFF if full.WhichOneof("FullFeedUnion")=="marketFF" else full.indexFF
            if ff.HasField("ltpc"): out.update({"ltp":ff.ltpc.ltp,"ltt":ff.ltpc.ltt,"cp":ff.ltpc.cp})
            if hasattr(ff,"vtt"): out["vtt"]=ff.vtt
            if ff.HasField("marketOHLC"):
                for candle in ff.marketOHLC.ohlc:
                    if candle.interval=="I1": out["i1"]={"open":candle.open,"high":candle.high,"low":candle.low,"close":candle.close,"volume":candle.vol,"ts":candle.ts}
                    elif candle.interval=="I30": out["i30"]={"open":candle.open,"high":candle.high,"low":candle.low,"close":candle.close,"volume":candle.vol,"ts":candle.ts}
        return out
