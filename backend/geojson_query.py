# -*- coding: utf-8 -*-
import os
import geopandas as gpd

class GeoJSONQueryEngine:
    def __init__(self, roads_path, subway_path):
        self.roads_path = roads_path
        self.subway_path = subway_path
        
    def get_all_vector_tracks(self):
        """一键展开全量交通骨架：读取并统一返回标准的经纬度 WGS84 格式供 Leaflet 铺底画线"""
        result = {"roads": None, "subways": None}
        
        if os.path.exists(self.roads_path):
            r_gdf = gpd.read_file(self.roads_path)
            if r_gdf.crs and r_gdf.crs != "EPSG:4326":
                r_gdf = r_gdf.to_crs(epsg=4326)
            result["roads"] = json.loads(r_gdf.to_json())
            
        if os.path.exists(self.subway_path):
            s_gdf = gpd.read_file(self.subway_path)
            if s_gdf.crs and s_gdf.crs != "EPSG:4326":
                s_gdf = s_gdf.to_crs(epsg=4326)
            result["subways"] = json.loads(s_gdf.to_json())
            
        return result