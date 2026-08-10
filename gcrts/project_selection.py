"""Shared in-process and file-backed selection for separate tool windows."""
import json,time
from pathlib import Path
class ProjectSelection:
    def __init__(self):self.asset_id=None;self._listeners=[]
    def subscribe(self,listener):self._listeners.append(listener);return lambda:self._listeners.remove(listener)
    def select_asset(self,asset_id,source=None):
        self.asset_id=asset_id
        for listener in tuple(self._listeners):listener(asset_id,source)

class FileProjectSelection:
    def __init__(self,path="project_selection.json"):self.path=Path(path)
    def select_asset(self,asset_id,source=None):self.path.write_text(json.dumps({"asset_id":asset_id,"source":source,"timestamp":time.time()},indent=2),encoding="utf-8")
    def current(self):
        if not self.path.exists():return None
        try:return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):return None
