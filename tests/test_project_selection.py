from gcrts.project_selection import ProjectSelection
def test_global_selection_notifies_both_directions():
    selection=ProjectSelection();seen=[];selection.subscribe(lambda asset,source:seen.append((asset,source)));selection.select_asset("main_menu.start","visual");selection.select_asset("category.photos","browser");assert seen==[("main_menu.start","visual"),("category.photos","browser")]
def test_file_selection_crosses_process_boundary(tmp_path):
    from gcrts.project_selection import FileProjectSelection
    a=FileProjectSelection(tmp_path/"selection.json");b=FileProjectSelection(tmp_path/"selection.json");a.select_asset("category.photos","visual");assert b.current()["asset_id"]=="category.photos"
