# -*- coding: utf-8 -*-
import os
import json

class LocalGraphEngine:
    def __init__(self):
        print("====== [KG Engine] 正在将多层知识网络全量加载至内存中 ======")
        self.nodes = {}
        self.bidirectional_index = {"topology": {}, "spatial": {}, "semantic": {}, "directional": {}}
        self._load_all_data()

    def _load_json(self, path):
        if not os.path.exists(path): return []
        with open(path, "r", encoding="utf-8") as f: return json.load(f)

    def _load_all_data(self):
        node_files = [
            ("../frontend/data/data/road_nodes_final.json", "Road"),
            ("../frontend/data/data/subway_nodes_final.json", "Subway"),
            ("../frontend/data/data/station_nodes_final.json", "Station"),
            ("../frontend/data/data/poi_nodes_final.json", "POI"),
            ("../frontend/data/data/water_nodes_final.json", "Water")
        ]
        for path, label in node_files:
            for n in self._load_json(path):
                self.nodes[str(n["entity_id"])] = {
                    "entity_id": str(n["entity_id"]), "name": str(n["name"]), 
                    "label": label, "properties": n.get("properties", {})
                }
        
        rel_configs = [
            ("../frontend/data/relationship/knowledge_graph.json", "topology"),
            ("../frontend/data/relationship/spatial_semantic_relations.json", "spatial"),
            ("../frontend/data/relationship/directional_relations.json", "directional")
        ]
        for path, layer in rel_configs:
            for edge in self._load_json(path):
                src = str(edge["source_id"])
                tgt = str(edge["target_id"])
                if src not in self.bidirectional_index[layer]: self.bidirectional_index[layer][src] = []
                if tgt not in self.bidirectional_index[layer]: self.bidirectional_index[layer][tgt] = []
                # 双向挂载，保障点击任何节点都能查出边
                self.bidirectional_index[layer][src].append(edge)
                if src != tgt: 
                    self.bidirectional_index[layer][tgt].append(edge)

    def _generate_property_nodes(self, entity_id):
        """【核心突破】：将隐藏的字典裂变成真实的实体节点！"""
        entity_id = str(entity_id)
        if entity_id not in self.nodes: return {}, []
        
        target_node = self.nodes[entity_id]
        props = target_node.get("properties", {})
        nodes_dict = {}
        edges_list = []
        
        # 1. 经纬度变节点
        if "lon" in props and "lat" in props:
            cid = f"coord_{entity_id}"
            nodes_dict[cid] = {"entity_id": cid, "name": f"({props['lon']}, {props['lat']})", "label": "Coordinate", "properties": {}}
            edges_list.append({"source_id": entity_id, "target_id": cid, "relation": "HAS_COORDINATE"})
            
        # 2. 其他属性全面裂变为节点 (如 highway=primary)
        for k, v in props.items():
            if isinstance(v, (list, dict)) or k == "original_ids": continue
            pid = f"prop_{entity_id}_{k}"
            label = "OSMTag" if k in ["highway", "railway", "amenity", "water", "natural"] else "Property"
            nodes_dict[pid] = {
                "entity_id": pid, 
                "name": f"{k}={v}", # 名字直接就是键值对！
                "label": label, 
                "properties": {}
            }
            edges_list.append({"source_id": entity_id, "target_id": pid, "relation": f"HAS_{label.upper()}"})
            
        return nodes_dict, edges_list

    def get_all_initial_data(self):
        """初始界面：全景节点 + 基础拓扑网"""
        all_topo_edges = []
        seen_edges = set()
        for edges in self.bidirectional_index["topology"].values():
            for e in edges:
                edge_hash = f"{e['source_id']}_{e['target_id']}_{e['relation']}"
                if edge_hash not in seen_edges:
                    seen_edges.add(edge_hash)
                    all_topo_edges.append(e)
        return {"nodes": list(self.nodes.values()), "edges": all_topo_edges}

    def get_node_subgraph(self, entity_id):
        """双击聚焦：节点 + 基础拓扑网 + 裂变后的属性实体树"""
        entity_id = str(entity_id)
        if entity_id not in self.nodes: return {"nodes": [], "edges": []}
        
        sub_nodes = {entity_id: self.nodes[entity_id]}
        sub_edges = []
        seen_edges = set()
        
        # 1. 加载基础拓扑
        for edge in self.bidirectional_index["topology"].get(entity_id, []):
            edge_hash = f"{edge['source_id']}_{edge['target_id']}_{edge['relation']}"
            if edge_hash not in seen_edges:
                seen_edges.add(edge_hash)
                sub_edges.append(edge)
                tgt = edge["target_id"] if edge["source_id"] == entity_id else edge["source_id"]
                if tgt in self.nodes: sub_nodes[tgt] = self.nodes[tgt]

        # 2. 加载裂变的实体化属性节点
        prop_nodes, prop_edges = self._generate_property_nodes(entity_id)
        sub_nodes.update(prop_nodes)
        sub_edges.extend(prop_edges)

        return {"nodes": list(sub_nodes.values()), "edges": sub_edges}

    def get_relations_by_layer(self, entity_id, layer_type):
        """右键特定扩展菜单查询：单独抓取方位/空间/属性等特定树"""
        entity_id = str(entity_id)
        if layer_type == "semantic":
            # 如果右键选了“展开属性”，则直接裂变生成属性树并返回
            sub_nodes = {entity_id: self.nodes[entity_id]} if entity_id in self.nodes else {}
            p_nodes, p_edges = self._generate_property_nodes(entity_id)
            sub_nodes.update(p_nodes)
            return {"nodes": list(sub_nodes.values()), "edges": p_edges}

        # 否则读取物理方位/空间等特定图层
        sub_nodes = {entity_id: self.nodes[entity_id]} if entity_id in self.nodes else {}
        sub_edges = []
        seen_edges = set()
        for edge in self.bidirectional_index[layer_type].get(entity_id, []):
            edge_hash = f"{edge['source_id']}_{edge['target_id']}_{edge['relation']}"
            if edge_hash not in seen_edges:
                seen_edges.add(edge_hash)
                sub_edges.append(edge)
                tgt = edge["target_id"] if edge["source_id"] == entity_id else edge["source_id"]
                if tgt in self.nodes: sub_nodes[tgt] = self.nodes[tgt]
        return {"nodes": list(sub_nodes.values()), "edges": sub_edges}