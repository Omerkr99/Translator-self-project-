"""Manually verified Twilight Syndrome asset registry."""
from __future__ import annotations

from gcrts.asset_descriptor import *
from gcrts.asset_compression import discover_streams
from gcrts.asset_tim import decode_tim

GAME = "Twilight Syndrome: Tansaku Hen"
TIM_CAPS = AssetCapabilities(True,True,True,True,True,True,True,True,False)

MENUDAT_SEMANTICS = {
    0:("menu.view_spoils","View Spoils","system_menu"),
    1:("menu.window_color","Window Color","system_menu"),
    2:("menu.return_to_title","Return to Title","system_menu"),
    3:("chapter.rumor_1","Rumor 1 — Spirit-photo Park","chapter_title"),
    4:("chapter.rumor_2","Rumor 2 — Music Room M.F.","chapter_title"),
    5:("chapter.rumor_3","Rumor 3 — Last Train","chapter_title"),
    6:("chapter.rumor_4","Rumor 4 — Seven Mysteries","chapter_title"),
    7:("main_menu.start","Start","button_label"),
    8:("main_menu.prepare","Prepare","button_label"),
    9:("category.photos","Photos","category_label"),
    10:("photo.park.koube_bridge","Park — Koube Bridge","photo_label"),
    11:("photo.park.front_of_toilet","Park — In Front of Toilet","photo_label"),
    12:("photo.park.midnight_torii","Park — Midnight Great Torii","photo_label"),
    13:("photo.park.parking_lot","Park — Parking Lot","photo_label"),
    14:("photo.m_station.womens_toilet","M Station — Women's Toilet","photo_label"),
    15:("photo.m_station.mens_toilet","M Station — Men's Toilet","photo_label"),
    16:("photo.m_station.walkway","M Station — Connecting Walkway","photo_label"),
    17:("photo.m_station.soba_shop","M Station — Soba Shop","photo_label"),
    18:("photo.m_station.platform_3","M Station — Platform 3","photo_label"),
    19:("photo.m_station.vending_machine","M Station — Vending Machine","photo_label"),
    20:("photo.m_station.platform_4","M Station — Platform 4","photo_label"),
    21:("photo.m_station.yuyamigaoka_bound","M Station — Yuyamigaoka-bound","photo_label"),
    22:("photo.hinashiro_high.gym_storage","Hinashiro High — Gym Equipment Room","photo_label"),
    23:("photo.waterworks.town_view","Town View from Waterworks","photo_label"),
    24:("category.live_recordings","Live Recordings","category_label"),
    25:("sound.sculpture_hall","Voice in Sculpture Hall","sound_label"),
    26:("sound.koube_bridge","Voice at Koube Bridge","sound_label"),
    27:("sound.midnight_school_broadcast","Midnight School Broadcast","sound_label"),
    28:("sound.midnight_piano","Midnight Piano","sound_label"),
    29:("sound.library","Voice in Library","sound_label"),
    30:("sound.air_raid_shelter","Voice in Air-raid Shelter","sound_label"),
    31:("photo.park.noon_torii","Park — Midday Great Torii","photo_label"),
}


def descriptors_for_file(data: bytes, disc_path: str) -> list[AssetDescriptor]:
    expected = 32 if "MENUDAT" in disc_path.upper() else 15 if "PROGDAT" in disc_path.upper() else None
    records = discover_streams(data, expected)
    result=[]
    for record in records:
        tim=decode_tim(record.decoded)
        known=False;name=f"Block {record.block}";usage="unknown"
        if "MENUDAT" in disc_path.upper() and record.block in MENUDAT_SEMANTICS:
            known=True;asset_id,name,usage=MENUDAT_SEMANTICS[record.block]
        elif "PROGDAT" in disc_path.upper() and record.block<5:
            known=True;name=f"Classroom background strip {record.block}";usage="background"
            asset_id=f"main_menu.classroom_background.strip_{record.block}"
        else:
            prefix="menudat" if "MENUDAT" in disc_path.upper() else "progdat"
            asset_id=f"{prefix}.unknown.block_{record.block}"
        mapping=ScreenMapping("MANUAL_VERIFIED",(65,200,100,24)) if record.block==7 and "MENUDAT" in disc_path.upper() else ScreenMapping("MANUAL_VERIFIED",(160,200,100,24)) if record.block==8 and "MENUDAT" in disc_path.upper() else ScreenMapping()
        descriptor=AssetDescriptor(asset_id,name,GAME,AssetSource("disc_file",disc_path),
            ContainerLocation("concatenated_compressed_streams",record.block,record.offset,record.consumed_size,len(record.decoded)),
            ImageMetadata(tim.format_name,tim.width,tim.height,len(tim.palette)),
            EncodingPolicy(SizePolicy.EXACT_CONSUMED_SIZE,record.consumed_size),
            SemanticStatus.KNOWN_SEMANTIC if known else SemanticStatus.UNKNOWN_SEMANTIC,usage,mapping,
            runtime={"selected_state":"LIVE_OBSERVED_COLOR_CHANGE" if record.block in (7,8) and "MENUDAT" in disc_path.upper() else "UNKNOWN",
                     "color_mechanism":"UNKNOWN"},
            verification={"decoded":True,"edited_live":record.block in (7,8) and "MENUDAT" in disc_path.upper(),
                          "reinjected_live":record.block in (7,8) and "MENUDAT" in disc_path.upper()},capabilities=TIM_CAPS)
        result.append(descriptor)
    return result
