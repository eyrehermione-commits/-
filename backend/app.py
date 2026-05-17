from flask import Flask
from flask import jsonify
from flask_cors import CORS

from neo4j_query import *

app = Flask(__name__)

CORS(app)

# =========================
# 节点
# =========================

@app.route("/node/<node_id>")

def get_node(node_id):

    return jsonify(
        query_node(node_id)
    )

# =========================
# 关系
# =========================

@app.route(
    "/relations/<node_id>"
)

def get_relations(node_id):

    return jsonify(
        query_relations(node_id)
    )

if __name__ == "__main__":

    app.run(
        debug=True
    )