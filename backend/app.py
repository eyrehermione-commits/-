# -*- coding: utf-8 -*-
import os
import json
from flask import Flask, jsonify, request
from flask_cors import CORS
from neo4j_query import LocalGraphEngine

app = Flask(__name__)
CORS(app)

graph_kernel = LocalGraphEngine()

def load_raw_geojson(path_options):
    for path in path_options:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                try: return json.load(f)
                except: continue
    return {"type": "FeatureCollection", "features": []}

@app.route("/api/init", methods=["GET"])
def get_initial_graph():
    return jsonify({"status": "success", "data": graph_kernel.get_all_initial_data()})

@app.route("/api/node/subgraph", methods=["GET"])
def get_node_subgraph():
    eid = request.args.get("entity_id")
    return jsonify({"status": "success", "data": graph_kernel.get_node_subgraph(eid)})

@app.route("/api/node/relations", methods=["GET"])
def get_node_expanded_relations():
    eid = request.args.get("entity_id")
    layer = request.args.get("layer")
    return jsonify({"status": "success", "data": graph_kernel.get_relations_by_layer(eid, layer)})

@app.route("/api/geo/raw-layers", methods=["GET"])
def get_raw_geojson_layers():
    # 使用数组尝试匹配有 s 和没 s 的文件命名习惯
    layers = {
        "roads": load_raw_geojson(["../frontend/data/roads.geojson", "../frontend/data/road.geojson"]),
        "subways": load_raw_geojson(["../frontend/data/subways.geojson", "../frontend/data/subway.geojson"]),
        "stations": load_raw_geojson(["../frontend/data/stations.geojson", "../frontend/data/station.geojson"]),
        "pois": load_raw_geojson(["../frontend/data/pois.geojson", "../frontend/data/poi.geojson"]),
        "water": load_raw_geojson(["../frontend/data/water.geojson", "../frontend/data/waters.geojson"])
    }
    return jsonify({"status": "success", "data": layers})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)