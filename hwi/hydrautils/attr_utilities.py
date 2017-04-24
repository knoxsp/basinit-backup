import hydra_connector as hc
from HydraServer.lib.objects import JSONObject

def create_attr(attr, user_id):
    return JSONObject(hc.add_attr(attr, user_id=user_id))

def get_all_attributes():
    return [JSONObject(a) for a in hc.get_all_attributes()]
