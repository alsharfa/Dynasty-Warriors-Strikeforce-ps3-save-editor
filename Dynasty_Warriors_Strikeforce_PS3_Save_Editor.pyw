#!/usr/bin/env python3
"""
Dynasty Warriors: Strikeforce PS3 Save Editor
Target: BLES00825 / decrypted APP.BIN

The editor preserves unknown bytes and validates the fixed BLES00825 PS3 save layout.
The normal UI exposes only fields backed by real PS3 APP.BIN comparisons and/or
BLES00825 game-data structure evidence. Experimental Movie writes were removed in v4.0.
"""
from __future__ import annotations

import datetime as _dt
import os
import shutil
import struct
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_VERSION = (RESOURCE_ROOT / "VERSION").read_text(encoding="utf-8").strip()
APP_TITLE = f"Dynasty Warriors: Strikeforce PS3 Save Editor v{APP_VERSION}"

APP_SIZE = 0x48064
SLOT_SIZE = 0x18000
SLOT_COUNT = 3
GLOBAL_TAIL = 0x64
EXPECTED_TITLE_ID = "BLES00825"
EXPECTED_SAVE_FILENAME = "APP.BIN"
FORMAT_LABEL = "BLES00825 / APP.BIN / 3 x 0x18000 + 0x64"
assert SLOT_SIZE * SLOT_COUNT + GLOBAL_TAIL == APP_SIZE

# ---------------------------------------------------------------------------
# Verified BLES00825 offsets (slot-relative)
# ---------------------------------------------------------------------------
OFF_GOLD = 0x1588

# Correct selected-officer runtime record. v3.3 and earlier accidentally
# treated 0x00DE as a level field, but it is the low halfword of the 32-bit EXP
# value. Direct comparison with the persistent 42-officer records establishes:
#   +04 officer ID (u8), +05 status (u8), +06 Level (BE16), +08 EXP (BE32),
#   +0C six weapon proficiencies (BE16), +18 six ability stats (BE16).
OFF_SELECTED_RECORD = 0x00D4
OFF_SELECTED_ID = OFF_SELECTED_RECORD + 0x04       # 0x00D8
OFF_SELECTED_STATUS = OFF_SELECTED_RECORD + 0x05   # 0x00D9
OFF_SELECTED_LEVEL = OFF_SELECTED_RECORD + 0x06    # 0x00DA
OFF_SELECTED_EXP = OFF_SELECTED_RECORD + 0x08      # 0x00DC
OFF_SELECTED_XP = OFF_SELECTED_RECORD + 0x0C       # 0x00E0

# The public all-material patch writes a 204-byte block at 0x09B0, but the
# actual 196 editable storehouse rows start eight bytes later at 0x09B8.
# This alignment is forced by the 196-byte owned array at 0x0A7C and the
# 196-byte quantity array at 0x0B44. v2.4 incorrectly paired row 0 with
# 0x09B0, shifting every material eight rows away from its flag/quantity.
OFF_INVENTORY_ID_BLOCK = 0x09B0
INVENTORY_ID_PREFIX = 8
OFF_INVENTORY_IDS = OFF_INVENTORY_ID_BLOCK + INVENTORY_ID_PREFIX  # 0x09B8
OFF_INVENTORY_FLAGS = 0x0A7C
OFF_INVENTORY_QTY = 0x0B44
INVENTORY_SLOTS = 196

# Correct persistent officer record base. The 12 proficiency/ability values
# begin at 0x1880 for officer 0, but the full record starts at 0x1874.
# Older builds wrote the EXP low halfword when they claimed to edit Level.
OFF_OFFICER_RECORDS = 0x1874
OFFICER_RECORD_SIZE = 0x40
OFFICER_COUNT = 42
OFFICER_ID_REL = 0x04
OFFICER_STATUS_REL = 0x05
OFFICER_LEVEL_REL = 0x06
OFFICER_EXP_REL = 0x08
OFFICER_XP_REL = 0x0C
OFFICER_MAIN_WEAPON_REL = 0x28
OFFICER_SUB_WEAPON_REL = 0x2A
OFF_OFFICER_XP = OFF_OFFICER_RECORDS + OFFICER_XP_REL  # 0x1880 compatibility alias

# Two equipped weapon instances in the selected-officer runtime block. These
# are 100-byte records matching LINKDATA 00006.bin's weapon record layout.
OFF_EQUIPPED_MAIN = 0x012E
OFF_EQUIPPED_SUB = 0x0192
WEAPON_RECORD_SIZE = 100
WEAPON_DB_RECORD_COUNT = 299

# ---------------------------------------------------------------------------
# Collection/unlock tables.
#
# These offsets are PS3-confirmed by structure and are correlated to known
# Dynasty Warriors: Strikeforce PSP CWCheat collection arrays using the same
# relative save layout. The BLES00825 sample has exactly the expected 0/1
# patterns at these locations.
# ---------------------------------------------------------------------------
OFF_WEAPON_FLAGS = 0x03E2
WEAPON_FLAG_COUNT = 284
ORB_RANGES = ((0x061A, 54), (0x068A, 40))       # BE16 values
CHI_RANGES = ((0x06E2, 110), (0x07D6, 60), (0x085E, 4))  # BE16 values
OFF_CARD_FLAGS = 0x0872
CARD_COUNT = 100                                  # BE16 values
OFF_TREASURE_FLAGS = 0x093A
TREASURE_COUNT = 20                               # BE16 values

# PS3 port inserts 0x200 bytes before the late PSP slot tail. The PSP "All
# Movies" array maps to this observed PS3 region. Kept explicitly labelled
# experimental in the UI rather than silently treating it as fully verified.
OFF_MOVIE_FLAGS = 0x15B5
MOVIE_COUNT = 43                                  # u8 values

# ---------------------------------------------------------------------------
# City facility development (slot-relative) — BLES00825 PS3 save-validated mapping.
#
# Original PSP CWCheat data places the 6 x u8 city level array immediately
# after the late gallery/movie region, followed by six city EXP values. The
# PS3 port shifts this late-save region by +0x200 bytes (the same shift already
# used for Movies), mapping City Levels to 0x1618 and City EXP to 0x161E.
# Facility order follows the in-game shop order. City EXP 4990 (0x137E) is the
# published near-full gauge value used before the post-battle update.
# ---------------------------------------------------------------------------
OFF_CITY_LEVELS = 0x1618
OFF_CITY_EXP = 0x161E
CITY_FACILITIES = (
    "Blacksmith", "Workshop", "Academy", "Exchange", "Market", "Storehouse",
)
CITY_FACILITY_COUNT = len(CITY_FACILITIES)
CITY_LEVEL_MAX = 5
CITY_EXP_NEAR_FULL = 4990

# ---------------------------------------------------------------------------
# Story / Request records (slot-relative) — PS3 BLES00825
#
# v3.0 correction:
# Every saved StorySet block has an 8-byte wrapper. The actual 150 x 12-byte
# tables begin at 0x6460, 0x6B68 and 0x7270, verified byte-for-byte against
# LINKDATA StorySetGi.bin / StorySetGo.bin / StorySetShoku.bin.
#
# Record layout:
# +00 record index (FF unused), +01 force, +02 chapter, +03 category,
# +05 quest ID, +06 dependency/link, +07/+08/+09/+0A runtime state.
#
# APP(8).BIN also proved that the StorySet state is not the only chapter gate:
# slot+0x0200 is 0x05 in that failed-unlock save, while an all-faction-story-
# cleared PS3 reference save has 0x07. Unlock All Chapters therefore sets this
# global postgame progression byte as well as the aligned StorySet availability
# states. State C/D (+09/+0A) are preserved.
# ---------------------------------------------------------------------------
STORYSET_BLOCK_BASES = (0x6460, 0x6B68, 0x7270)
STORYSET_BLOCK_NAMES = ("Wei", "Wu", "Shu")
STORYSET_RECORD_SIZE = 12
STORYSET_RECORDS_PER_BLOCK = 150
STORYSET_RECORD_INDEX_REL = 0x00
STORYSET_FORCE_REL = 0x01
STORYSET_CHAPTER_REL = 0x02
STORYSET_CATEGORY_REL = 0x03
STORYSET_QUEST_ID_REL = 0x05
STORYSET_LINK_REL = 0x06
STORYSET_STATE_A_REL = 0x07
STORYSET_STATE_B_REL = 0x08
STORYSET_STATE_C_REL = 0x09
STORYSET_STATE_D_REL = 0x0A
STORYSET_CATEGORY_STORY = 0
STORYSET_CATEGORY_REQUEST = 1
STORYSET_FIRST_CHAPTER = 1
STORYSET_LAST_CHAPTER = 6

OFF_STORY_PROGRESS = 0x0200
STORY_PROGRESS_POSTGAME = 0x07

PROFICIENCY_NAMES = ["Sword", "Spear", "Pike", "Cudgel", "Bow", "Tech"]
OFFICER_ABILITY_NAMES = ["Life", "Fury", "Attack", "Defense", "Move", "Resist"]
XP_NAMES = PROFICIENCY_NAMES + OFFICER_ABILITY_NAMES
OFFICER_STAT_LABELS = [name + " proficiency" for name in PROFICIENCY_NAMES] + [name + " ability" for name in OFFICER_ABILITY_NAMES]
OFFICER_LEVEL_MAX = 50
OFFICER_QUICK_EXP = 50000
OFFICER_PROFICIENCY_MAX = 1000
OFFICER_ABILITY_MAX = 500

OFFICERS = [
    "Xiahou Dun", "Dian Wei", "Sima Yi", "Zhang Liao", "Cao Cao", "Xu Zhu",
    "Xiahou Yuan", "Xu Huang", "Zhang He", "Cao Ren", "Cao Pi", "Zhen Ji",
    "Zhou Yu", "Lu Xun", "Sun Shang Xiang", "Gan Ning", "Sun Jian", "Taishi Ci",
    "Lu Meng", "Huang Gai", "Zhou Tai", "Ling Tong", "Sun Ce", "Sun Quan",
    "Xiao Qiao", "Zhao Yun", "Guan Yu", "Zhang Fei", "Zhuge Liang", "Liu Bei",
    "Ma Chao", "Huang Zhong", "Wei Yan", "Guan Ping", "Pang Tong", "Yue Ying",
    "Diao Chan", "Lu Bu", "Dong Zhuo", "Yuan Shao", "Zhang Jiao", "Meng Huo",
]

# Playable-roster force grouping in the same order as OFFICERS.
# Keeping this as display metadata avoids exposing raw numeric officer IDs.
OFFICER_FORCES = (["Wei"] * 12) + (["Wu"] * 13) + (["Shu"] * 11) + (["Other"] * 6)
assert len(OFFICER_FORCES) == len(OFFICERS)


# Exact BLES00825 "Have All Materials" ID bytes from the public Game Genie /
# Apollo patch. The first 196 bytes are the storehouse's materials; the last
# 8 bytes spill into the four unused rows used by the original patch sequence.
ALL_MATERIAL_IDS = bytes.fromhex(
    "0007000e7639020304053a3b630c9f0e"
    "101112401513181900a70a3d419a3c3e"
    "454695ba80964b6644999b5f8f94989e"
    "9c868b4e06070b0d500f28ae4f3816b7"
    "481a1b01495309b5141c1d1e1f209d4c"
    "29922c2e6dab33bbb6082b34377d6773"
    "687781717bad7c937ea4434a78518391"
    "47a97fac8cb4729785798a907a878824"
    "25262d2f30313258213570362327222a"
    "426b3f574d526eb984a1aa8d566064a6"
    "656a74afb08259895b5c5d5e8e62b154"
    "6f6c695575a0a2b8a3a8a569c56c5a87"
    "615f6062676d6eb3576fb255"
)
assert len(ALL_MATERIAL_IDS) == 204
ALL_MATERIAL_ROW_IDS = ALL_MATERIAL_IDS[INVENTORY_ID_PREFIX:]
assert len(ALL_MATERIAL_ROW_IDS) == INVENTORY_SLOTS

ABILITY_NONE = 0x26
ABILITY_NAMES = {
    0x02: "Attack Boost",
    0x03: "Defense",
    0x04: "Move",
    0x05: "Resist",
    0x06: "Hit / Critical Boost",
    0x07: "Wood",
    0x08: "Fire",
    0x09: "Earth",
    0x0A: "Metal",
    0x0B: "Water",
    0x0C: "Dark",
    0x0D: "Light",
    0x15: "Range",
    0x16: "Attack Speed",
    0x17: "Regular Attack",
    0x18: "Power Attack",
    0x19: "Special Attack",
    0x1A: "Musou",
    0x1B: "Fury Attack",
    0x1C: "Chain",
    0x1F: "Stun",
    0x24: "Bellow",
    0x25: "Luck",
    ABILITY_NONE: "None",
}

# ---------------------------------------------------------------------------
# Name database
# ---------------------------------------------------------------------------
# The save continues to store numeric IDs.  The editor translates IDs to names
# for display, but always keeps the numeric value visible so round-tripping is
# lossless and unknown IDs are never guessed.
#
# Weapons 0..167 are the 42 PS3 officers x 4 personal weapons in the exact
# officer order used by LINKDATA 00006.bin.  Generic/master weapons continue at
# 168; the entries below are mapped only where the name is confirmed.
OFFICER_UNIQUE_WEAPONS = {
    "Xiahou Dun": ["Rock Crusher", "Wave Breaker", "Thundersmash", "Pulverizer"],
    "Dian Wei": ["Violent Soul Star", "Lion's Head Star", "Berserker Star", "Demon Star"],
    "Sima Yi": ["Eradication Claws", "Anguish Claws", "Necrosis Claws", "Purgatory Claws"],
    "Zhang Liao": ["Twin Vipers", "Twin Dragons", "Twin Eagles", "Twin Beasts"],
    "Cao Cao": ["Sword of Heaven", "Blue Blade", "Seven Star Sword", "Sword of Dread"],
    "Xu Zhu": ["Bone Crusher", "Chaos Crusher", "Whirlwind Crusher", "Beast Crusher"],
    "Xiahou Yuan": ["Swallow Bow", "Raven Bow", "Falcon Bow", "Eagle Bow"],
    "Xu Huang": ["Destroyer", "Annihilator", "Obliterator", "Exterminator"],
    "Zhang He": ["Phoenix Talons", "Dragon Claws", "White Tigers", "Phantom Claws"],
    "Cao Ren": ["Phoenix Wing", "Dragon Scale", "Tortoise Bite", "Warrior's Code"],
    "Cao Pi": ["Heaven's Blade", "Kingdom's Pride", "Leader of Men", "Judgement Blade"],
    "Zhen Ji": ["Allure", "Charm", "Seduction", "Temptation"],
    "Zhou Yu": ["Red Dusk", "Dark Night", "Scarlet Dawn", "Crimson Sun"],
    "Lu Xun": ["Silver Swallow", "Blue Falcon", "Jade Warbler", "Radiant Eagle"],
    "Sun Shang Xiang": ["Madder Rose", "Wisteria Breeze", "Lotus Bow", "Royal Orchid"],
    "Gan Ning": ["Crescent Moons", "Dancing Dragons", "Wing Blades", "Blazing Stars"],
    "Sun Jian": ["Elder Sword", "Nine Hook Sword", "Golden Phoenix", "Ancients' Sword"],
    "Taishi Ci": ["Wolf Slayer", "Tiger Slayer", "Apollyon", "Armageddon"],
    "Lu Meng": ["Valor", "Spirit", "Courage", "Justice"],
    "Huang Gai": ["River Slicer", "Mountain Breaker", "Sky Lasher", "Ocean Splitter"],
    "Zhou Tai": ["Flashstrike", "Dawnstrike", "Duskstrike", "Solarstrike"],
    "Ling Tong": ["Cyclone", "Typhoon", "Hurricane", "Tornado"],
    "Sun Ce": ["Tyrant Strike", "Glimmer Strike", "Stoic Strike", "Despot Strike"],
    "Sun Quan": ["Dragon's Might", "Heaven's Might", "Titan's Might", "Creation's Might"],
    "Xiao Qiao": ["True Grace", "True Beauty", "True Luster", "True Radiance"],
    "Zhao Yun": ["Dragon Spike", "Dragon Fang", "Dragon Talon", "Dragon Fire"],
    "Guan Yu": ["Blue Dragon", "Black Dragon", "White Dragon", "Yellow Dragon"],
    "Zhang Fei": ["Serpent Blade", "Python Blade", "Viper Blade", "Cobra Blade"],
    "Zhuge Liang": ["Brilliance", "Distinction", "Enlightenment", "Omniscience"],
    "Liu Bei": ["Strength and Virtue", "Heaven and Earth", "Yin and Yang", "Just and True"],
    "Ma Chao": ["Ruination", "Storm Breaker", "Mountain Mover", "Eon Slicer"],
    "Huang Zhong": ["Warrior Bow", "Veteran Bow", "Warlord Bow", "Conqueror Bow"],
    "Wei Yan": ["Awakener", "Bonesplitter", "Stormhowl", "Demon Rage"],
    "Guan Ping": ["Blue Dragon Ji", "Black Dragon Ji", "White Dragon Ji", "Rising Dragon Ji"],
    "Pang Tong": ["Firestorm Cane", "Blizzard Cane", "Typhoon Cane", "Feng Shen Cane"],
    "Yue Ying": ["Jade Crescent", "Sapphire Crescent", "Opal Crescent", "Golden Crescent"],
    "Diao Chan": ["Moonflower", "Dewflower", "Rainflower", "Deathflower"],
    "Lu Bu": ["Sky Piercer", "Demon Bane", "Heron Blade Halberd", "Eternity Piercer"],
    "Dong Zhuo": ["Gargoyle Club", "Mendes Club", "Malevolent Club", "Ogre Club"],
    "Yuan Shao": ["Sword of Kings", "Sword of Severity", "North Star Sword", "Sword of Destiny"],
    "Zhang Jiao": ["Blaze Cane", "Blight Cane", "Judgement Cane", "Tai Ping Cane"],
    "Meng Huo": ["Earth Shaker", "Storm Shaker", "Bane Shaker", "Inferno Shaker"],
}

FULL_WEAPON_NAMES = ['Rock Crusher', 'Wave Breaker', 'Thundersmash', 'Pulverizer', 'Violent Soul Star', "Lion's Head Star", 'Berserker Star', 'Demon Star', 'Eradication Claws', 'Anguish Claws', 'Necrosis Claws', 'Purgatory Claws', 'Twin Vipers', 'Twin Dragons', 'Twin Eagles', 'Twin Beasts', 'Sword of Heaven', 'Blue Blade', 'Seven Star Sword', 'Sword of Dread', 'Bone Crusher', 'Chaos Crusher', 'Whirlwind Crusher', 'Beast Crusher', 'Swallow Bow', 'Raven Bow', 'Falcon Bow', 'Eagle Bow', 'Destroyer', 'Annihilator', 'Obliterator', 'Exterminator', 'Phoenix Talons', "Dragon's Claws", 'White Tigers', 'Phantom Claws', 'Phoenix Wing', 'Dragon Scale', 'Tortoise Bite', "Warrior's Code", "Heaven's Blade", "Kingdom's Pride", 'Leader of Men', 'Judgment Blade', 'Allure', 'Charm', 'Seduction', 'Temptation', 'Red Dusk', 'Dark Night', 'Scarlet Dawn', 'Crimson Sun', 'Silver Swallow', 'Blue Falcon', 'Jade Warbler', 'Radiant Eagle', 'Madder Rose', 'Wisteria Breeze', 'Lotus Bow', 'Royal Orchid', 'Crescent Moons', 'Dancing Dragons', 'Wing Blades', 'Blazing Stars', 'Elder Sword', 'Nine Hook Sword', 'Golden Phoenix', "Ancients' Sword", 'Wolf Slayer', 'Tiger Slayer', 'Apollyon', 'Armageddon', 'Valor', 'Spirit', 'Courage', 'Justice', 'River Slicer', 'Mountain Breaker', 'Sky Lasher', 'Ocean Splitter', 'Flashstrike', 'Dawnstrike', 'Duskstrike', 'Solarstrike', 'Cyclone', 'Typhoon', 'Hurricane', 'Tornado', 'Tyrant Strike', 'Glimmer Strike', 'Stoic Strike', 'Despot Strike', "Dragon's Might", "Heaven's Might", "Titan's Might", "Creation's Might", 'True Grace', 'True Beauty', 'True Luster', 'True Radiance', 'Dragon Spike', 'Dragon Talon', 'Dragon Fire', 'Blue Dragon', 'Black Dragon', 'White Dragon', 'Serpent Blade', 'Python Blade', 'Viper Blade', 'Cobra Blade', 'Brilliance', 'Distinction', 'Enlightenment', 'Omniscience', 'Strength and Virtue', 'Heaven and Earth', 'Yin and Yang', 'Just and True', 'Ruination', 'Storm Breaker', 'Mountain Mover', 'Eon Slicer', 'Warrior Bow', 'Veteran Bow', 'Warlord Bow', 'Conqueror Bow', 'Awakener', 'Bone Splitter', 'Stormhowl', 'Demon Rage', 'Blue Dragon Ji', 'Black Dragon Ji', 'White Dragon Ji', 'Rising Dragon Ji', 'Firestorm Cane', 'Blizzard Cane', 'Typhoon Cane', 'Feng Shen Cane', 'Jade Crescent', 'Sapphire Crescent', 'Opal Crescent', 'Golden Crescent', 'Moonflower', 'Dewflower', 'Rainflower', 'Deathflower', 'Sky Piercer', 'Demon Bane', 'Heron Blade Halberd', 'Eternity Piercer', 'Gargoyle Club', 'Mendes Club', 'Malevolent Club', 'Ogre Club', 'Sword of Kings', 'Sword of Severity', 'North Star Sword', 'Sword of Destiny', 'Blaze Cane', 'Blight Cane', 'Judgment Cane', 'Tai Ping Cane', 'Earth Shaker', 'Storm Shaker', 'Bane Shaker', 'Inferno Shaker', 'Bronze Sword', 'Iron Sword', 'Steel Sword', 'Bravesword', 'Paladin Sword', 'Twin Gladii', 'Twin Brands', 'Twin Broadswords', 'Twin Falchions', 'Twin Glaives', 'Longblade', 'Nightblade', 'Razor Cutter', 'Beastmaster', 'Dragonslayer', 'Warrior Blade', 'Veteran Blade', 'Hero Blade', 'Warlord Blade', 'Eternity Blade', 'Machete', 'Katana', 'Scimitar', 'Cleaver', 'Aurablade', 'Twin Dirks', 'Twin Machetes', 'Twin Cleavers', 'Twin Hookblades', 'Twin Zodiacs', 'Violet Claw', 'Earthen Claw', 'Ebony Claw', 'Crimson Claw', 'Mystic Talon', 'Iron Spear', 'Blade Spear', 'Screw Spear', 'Guardian Spear', 'Paladin Spear', 'Iron Pike', 'Sentinel Pike', 'Moon Pike', 'Tiger Pike', 'Wu Shen Pike', 'Light Pikes', 'Fang Pikes', 'Talon Pikes', 'Wing Pikes', 'Demon Pikes', 'Crossed Iron', 'Crossed Steel', 'Crossed Onyx', 'Crossed Winds', 'Crossed Tigers', 'Stone Cudgel', 'Iron Cudgel', 'Fang Cudgel', 'Ram Cudgel', 'Dragon Cudgel', 'Wooden Staff', 'Iron Staff', 'Steel Staff', 'Noble Staff', 'Aura Staff', 'Stone Star', 'Iron Star', 'Steel Star', 'Blade Star', 'Eternal Star', 'Leather Flail', 'Iron Flail', 'Ornate Flail', 'Merciless Flail', 'Dragon Flail', 'Rock Maces', 'Sentinel Maces', 'Fable Maces', 'Jeweled Maces', 'Emperor Maces', 'Triple Strike', 'Azure Strike', 'Crimson Strike', 'Stygian Strike', 'Dragon Strike', 'Horn Bow', 'Compound Bow', 'Steel Bow', 'Winged Bow', "Heaven's Bow", 'Wood Bladebow', 'Steel Bladebow', 'Enigma Bladebow', 'Blaze Bladebow', 'Dragon Bladebow', 'Wooden Cane', 'Zen Cane', 'Shaman Cane', 'Mystic Cane', "Heaven's Cane", 'Military Fan', 'Azure Fan', 'Wing Fan', 'Guile Fan', "Heaven's Fan", 'Fang Gauntlets', 'Azure Gauntlets', 'Plated Gauntlets', 'Fire Gauntlets', 'Arcane Gauntlets', 'Peach Fan', 'Iron Fan', 'Crimson Fan', 'Ornate Fan', 'Peacock Fan', 'Bone Pillar', 'Fungus Pillar', 'Pine Pillar', 'Plantain Pillar', 'Gator Pillar', 'Dragon Sword', 'Fuma Kodachi', 'Heavenly Dragon Naginata', "Fu Xi's Sword", "Nu Wa's Rapier", 'Lightning Rod']
WEAPON_NAMES = dict(enumerate(FULL_WEAPON_NAMES))

# Complete PS3 material table recovered directly from the supplied
# BLES00825 EBOOT English material-name pointer table.  IDs are preserved
# exactly; unused/dummy IDs are explicitly labelled rather than hidden.
MATERIAL_NAMES = {
    0x00: "Short shard",
    0x01: "Long shard",
    0x02: "Wide shard",
    0x03: "Stone lump",
    0x04: "Old stick",
    0x05: "Waxwood",
    0x06: "Earth spirit",
    0x07: "Old charm",
    0x08: "Peasant book",
    0x09: "Obsidian",
    0x0A: "Malachite",
    0x0B: "Sand star",
    0x0C: "Bamboo",
    0x0D: "Cotton cloth",
    0x0E: "Flax cord",
    0x0F: "Black coal",
    0x10: "Leather",
    0x11: "Glue",
    0x12: "Hawk statue",
    0x13: "White pearl",
    0x14: "Amber",
    0x15: "Gold dust",
    0x16: "Crystal shard",
    0x17: "Impure oil",
    0x18: "Spring water",
    0x19: "Moonstone",
    0x1A: "Energy charm",
    0x1B: "Sunstone",
    0x1C: "Short iron blade",
    0x1D: "Long iron blade",
    0x1E: "Wide iron blade",
    0x1F: "Iron lump",
    0x20: "Iron rod",
    0x21: "Sturdy wood",
    0x22: "Beast spirit",
    0x23: "White charm",
    0x24: "Artisan book",
    0x25: "Spiritstone (s)",
    0x26: "Fireruby",
    0x27: "Firesand",
    0x28: "Peachwood",
    0x29: "Silk fabric",
    0x2A: "Silk thread",
    0x2B: "White coal",
    0x2C: "Feather",
    0x2D: "Bone crown",
    0x2E: "Orochi statue",
    0x2F: "Black pearl",
    0x30: "Jade",
    0x31: "Pink coral",
    0x32: "White crystal",
    0x33: "Spiritwater",
    0x34: "Fish oil",
    0x35: "Spiritgem",
    0x36: "Shiny charm",
    0x37: "Lifestone",
    0x38: "Steel blade (s)",
    0x39: "Steel blade (l)",
    0x3A: "Steel blade (w)",
    0x3B: "Steel sliver",
    0x3C: "Steel bar",
    0x3D: "Violet spiritwood",
    0x3E: "Warrior spirit",
    0x3F: "Aegis charm",
    0x40: "Strategist book",
    0x41: "Marble",
    0x42: "Nightstone",
    0x43: "Silversand",
    0x44: "Oakwood",
    0x45: "Gold cloth",
    0x46: "Leather cord",
    0x47: "Peach log",
    0x48: "Firescale",
    0x49: "Pelt",
    0x4A: "Wolf statue",
    0x4B: "Lapis lazuli",
    0x4C: "Ivory",
    0x4D: "Black coral",
    0x4E: "Amethyst",
    0x4F: "Varnish",
    0x50: "Lure water",
    0x51: "Large spiritgem",
    0x52: "Mortal amulet",
    0x53: "Light lump",
    0x54: "Rainbow blade (s)",
    0x55: "Rainbow blade (l)",
    0x56: "Rainbow blade (w)",
    0x57: "Diamond lump",
    0x58: "Platinum rod",
    0x59: "Banewood",
    0x5A: "King spirit",
    0x5B: "Mystery charm",
    0x5C: "Monarch book",
    0x5D: "Spiritstone (l)",
    0x5E: "Topaz",
    0x5F: "Rainbowsand",
    0x60: "Ebony",
    0x61: "Rainbow cloth",
    0x62: "Gold thread",
    0x63: "Rainbow cocoon",
    0x64: "Gold wing",
    0x65: "Beast horn",
    0x66: "Lord statue",
    0x67: "Silver shell",
    0x68: "Gold fang",
    0x69: "Rainbow chain",
    0x6A: "Citrine",
    0x6B: "Sundrop",
    0x6C: "Moondrop",
    0x6D: "Dark crystal",
    0x6E: "King's amulet",
    0x6F: "Meteor lump",
    0x70: "Mystic blade (s)",
    0x71: "Mystic blade (l)",
    0x72: "Mystic blade (w)",
    0x73: "Mystic lump",
    0x74: "Mystic rod",
    0x75: "Mystic spiritwood",
    0x76: "Mage spirit",
    0x77: "Arcane charm",
    0x78: "Mage book",
    0x79: "Ancient stone",
    0x7A: "Heaven gem",
    0x7B: "Mystic loam",
    0x7C: "Arcane wood",
    0x7D: "Wraith cloth",
    0x7E: "Wraith thread",
    0x7F: "Ancient leaf",
    0x80: "Giant scale",
    0x81: "Giant talon",
    0x82: "Phantom statue",
    0x83: "Phantom pillar",
    0x84: "Mystic alloy",
    0x85: "Ancient bangle",
    0x86: "Ancient crystal",
    0x87: "Phantom honey",
    0x88: "Mystic oil",
    0x89: "Mystic spiritgem",
    0x8A: "Mystic amulet",
    0x8B: "Sky garment",
    0x8C: "Dragon soul (b)",
    0x8D: "Phoenix soul",
    0x8E: "Dragon soul (y)",
    0x8F: "Tiger soul",
    0x90: "Warrior soul",
    0x91: "Earth gift",
    0x92: "Sky gift",
    0x93: "Fealty dagger",
    0x94: "E Lai chain",
    0x95: "Schemer's attire",
    0x96: "War teachings",
    0x97: "Wei helmet",
    0x98: "Tiger fool ring",
    0x99: "Sharp arrow",
    0x9A: "Warrior's blade",
    0x9B: "Beautiful art",
    0x9C: "Sturdy armor",
    0x9D: "Ice flower",
    0x9E: "Fancy ring",
    0x9F: "Dominion plan",
    0xA0: "Seal of office",
    0xA1: "Princess bow",
    0xA2: "Chivalrous bell",
    0xA3: "Legendary seal",
    0xA4: "Sign of promise",
    0xA5: "Bamboo scroll",
    0xA6: "Aged pouch",
    0xA7: "Herb bath",
    0xA8: "Torn duel",
    0xA9: "Little crown",
    0xAA: "Successor mark",
    0xAB: "Flower tiara",
    0xAC: "Spear shard",
    0xAD: "Zuo Zhuan",
    0xAE: "Peach juice",
    0xAF: "Chu Shi Biao",
    0xB0: "Ambition cup",
    0xB1: "Brocade rein",
    0xB2: "Veteran arrow",
    0xB3: "Bone candle",
    0xB4: "War god print",
    0xB5: "Linked chains",
    0xB6: "Wood art",
    0xB7: "Royal erhu",
    0xB8: "Warrior plume",
    0xB9: "Splendid grail",
    0xBA: "Noble treasure",
    0xBB: "Yellow turban",
    0xBC: "<Unused / Dummy 0>",
    0xBD: "<Unused / Dummy 1>",
    0xBE: "<Unused / Dummy 2>",
    0xBF: "<Unused / Dummy 3>",
    0xC0: "<Unused / Dummy 4>",
    0xC1: "<Unused / Dummy 5>",
    0xC2: "<Unused / Dummy 6>",
    0xC3: "<Unused / Dummy 7>",
    0xC4: "<Unused / Dummy 8>",
    0xC5: "Jungle Lava",
    0xC6: "<Unused / Dummy 9>",
    0xC7: "<Unused / Dummy 10>",
}

# IDs that represent real obtainable/material entries in the PS3 English table.
# 0xBC-0xC4 and 0xC6-0xC7 are unused/dummy entries; 0xC5 is Jungle Lava.
REAL_MATERIAL_IDS = [i for i in range(0x00, 0xBC)] + [0xC5]

MATERIAL_NAME_TO_ID = {name: item_id for item_id, name in MATERIAL_NAMES.items()}
WEAPON_NAME_TO_ID = {name: weapon_id for weapon_id, name in WEAPON_NAMES.items()}
ABILITY_NAME_TO_ID = {name: ability_id for ability_id, name in ABILITY_NAMES.items()}
WEAPON_CHOICES = [WEAPON_NAMES[i] for i in sorted(WEAPON_NAMES)]
MATERIAL_CHOICES = [MATERIAL_NAMES[i] for i in REAL_MATERIAL_IDS]
ABILITY_CHOICES = [ABILITY_NAMES[i] for i in sorted(ABILITY_NAMES)]

# Officer-card positions in the published in-game card order.  The original
# guide identifies cards #001-#099 by name; #100 was left unidentified, so
# that final slot remains explicitly unverified rather than guessed.
OFFICER_CARD_NAMES = [
    "Cao Cao", "Cao Pi", "Zhen Ji", "Xiahou Dun", "Dian Wei", "Xu Zhu",
    "Xiahou Yuan", "Zhang Liao", "Xu Huang", "Zhang He", "Cao Ren", "Sima Yi",
    "Guo Jia", "Cao Zhang", "Cao Zhi", "Jia Xu", "Li Dian", "Yue Jin", "Yu Jin",
    "Cao Hong", "Guo Huai", "Xiahou En", "Man Chong", "Niu Jin", "Xiahou Shang",
    "Sun Jian", "Sun Ce", "Sun Quan", "Sun Shang Xiang", "Zhou Yu", "Lu Xun",
    "Huang Gai", "Taishi Ci", "Lu Meng", "Gan Ning", "Zhou Tai", "Ling Tong",
    "Xiao Qiao", "Han Dang", "Yu Fan", "Zhu Ran", "Jiang Qin", "Zhuge Jin",
    "Sun Xiu", "Zhang Zhao", "Chen Wu", "Cheng Pu", "Xue Zong", "Ma Zhong", "Lu Su",
    "Liu Bei", "Guan Yu", "Zhang Fei", "Zhuge Liang", "Zhao Yun", "Ma Chao",
    "Huang Zhong", "Wei Yan", "Pang Tong", "Guan Ping", "Yue Ying", "Yi Ji", "Wang Ping",
    "Yan Yan", "Gao Ding", "Zhou Cang", "Zhang Bao", "Chen Shi", "Ma Su", "Ma Dai",
    "Fei Yi", "Mi Zhu", "Meng Da", "Lei Tong", "Liu Qi",
    "Lu Bu", "Diao Chan", "Dong Zhuo", "Yuan Shao", "Zhang Jiao", "Yuan Shu",
    "Wang Yun", "Liu Zhang", "Liu Biao", "He Jin", "Hua Xiong", "Gao Shun",
    "Huang Zu", "Gongsun Zan", "Huangfu Song", "Chunyu Qiong", "Su Fei", "Zhang Ren",
    "Zhang Bao", "Zhang Liang", "Zhang Lu", "Chen Gong", "Wen Chou", "Yan Liang",
]
assert len(OFFICER_CARD_NAMES) == 99

def officer_card_force(index: int) -> str:
    """Return the card's force grouping from the published card order."""
    if 0 <= index < 25:
        return "Wei"
    if 25 <= index < 50:
        return "Wu"
    if 50 <= index < 75:
        return "Shu"
    if 75 <= index < CARD_COUNT:
        return "Other"
    return ""

# Published Chi names in shop/list order.  The PS3 save exposes extra/reserved
# collection entries; those remain clearly labelled by index rather than guessed.
CHI_NAMES = [
    "Focus++", "Serendipity", "Restore++", "Channel+", "Readiness+", "Last Stand+",
    "Rush++", "Float+", "Vitality+", "Focus+", "Restore+", "Rear Guard", "Expanse",
    "Bolster", "Tamer", "Spring+", "Rush+", "Focus", "Leap+", "Restore", "Buoyant",
    "Insight", "Channel", "Bound", "Provoke", "Readiness", "Float", "Last Stand",
    "Spirit", "Acrobat", "Spring", "Rush", "Vitality", "Meta Heal", "Leap",
    "Immortal", "Poison Resist", "Engulf Resist", "Heavy Resist", "Stun Resist",
    "Ice Resist", "Seal Resist", "Release Resist", "Warden+", "Meta Absorb+",
    "Coup de Grace", "Charge++", "Poison Wave+", "Engulf Wave+", "Heavy Wave+",
    "Stun Wave+", "Ice Wave+", "Seal Wave+", "Disband Wave+", "Control++", "Pierce+",
    "Elemental+", "Absorb+", "Iron Armor+", "Musou Armor+", "Salvo+", "Diffusion+",
    "Fury Armor", "Fury Heal+", "Anthrostrike+", "Mechastrike+", "Invert+", "Maintain",
    "Fury Jolt+", "Fury Stun+", "Dart", "Chain", "Charge+", "Poison Wave", "Engulf Wave",
    "Heavy Wave", "Stun Wave", "Ice Wave", "Seal Wave", "Disband Wave", "Cooperation",
    "Warden", "Steel Skin", "Control+", "Meta Absorb", "Aero+", "Wraith Rush",
    "Iron Armor", "Musou Armor", "Pierce", "Elemental", "Absorb", "Swift Rush+",
    "Balance", "Anthrostrike", "Mechastrike", "Invert", "Salvo", "Diffusion",
    "Fury Heal", "Charge", "Control", "Aero", "Swift Rush", "Meta Defense",
    "Meta Attack", "Meta Resist", "Fury Jolt", "Fury Stun",
    "Musou Poison 4", "Musou Fire 4", "Musou Earth 4", "Musou Metal 4", "Musou Ice 4",
    "Musou Dark 4", "Musou Light 4", "Musou Sphere", "Musou Poison 3", "Musou Poison 5",
    "Musou Fire 3", "Musou Fire 5", "Musou Earth 3", "Musou Earth 5", "Musou Metal 3",
    "Musou Metal 5", "Musou Ice 3", "Musou Ice 5", "Musou Dark 3", "Musou Dark 5",
    "Musou Light 3", "Musou Light 5", "Musou Poison 2", "Musou Fire 2", "Musou Earth 2",
    "Musou Metal 2", "Musou Ice 2", "Musou Dark 2", "Musou Light 2", "Musou Dark 1",
    "Musou Light 1", "Musou Poison 1", "Musou Fire 1", "Musou Earth 1", "Musou Metal 1",
]


# In-game Treasure Vault order. This order is documented consistently by the
# achievement/trophy guides and corresponds to the 20-entry ownership array.
TREASURE_NAMES = [
    "Grand Histories",
    "Meng De's Manual",
    "Art of War",
    "24 War Manuals",
    "Book of Illusions",
    "Imperial Seal",
    "Dragon Ring",
    "Shadow Runner",
    "Awards of Valor",
    "Way of Peace",
    "He's Jade",
    "Red Hare",
    "War God Statue",
    "Banana Leaf Fan",
    "Mo Xie Sword",
    "5 Colored Stones",
    "Shan Hai Jing",
    "Bronze Pheasant",
    "4 Gods Statue",
    "Hex Mark",
]
assert len(TREASURE_NAMES) == TREASURE_COUNT

TREASURE_CONDITIONS = [
    "Complete Chapter 3 in any story",
    "Complete Wei Chapter 5",
    "Complete Wu Chapter 5",
    "Complete Shu Chapter 5",
    "Complete Chapter 6 in any story",
    "Complete about 100 quests",
    "Complete about 100 bonus objectives",
    "Win 10 different Legend quests",
    "Have 100+ stored items/materials, then complete a quest",
    "Complete a quest with every playable officer",
    "Reach Level 50 with a Musou officer",
    "Defeat Lu Bu 10 times",
    "Defeat all playable Musou officers as enemies",
    "Use a top-rank weapon with its related officer and complete a quest",
    "Learn all top-rank (5000G) Chi skills, then complete a quest",
    "Collect all top-rank (5000G) Orbs, then complete a quest",
    "Collect all playable-officer cards, then complete a quest",
    "Fully develop all six city facilities, then complete a quest",
    "Register 10 online players and complete an online quest with one",
    "Win 10 online VS battles",
]



def weapon_name(index: int) -> str:
    return WEAPON_NAMES.get(index, "Reserved / unknown weapon")


def material_name(item_id: int) -> str:
    return MATERIAL_NAMES.get(item_id, "Unknown material")


def collection_entry_name(collection: str, index: int) -> str:
    if collection == "Weapons":
        return weapon_name(index)
    if collection == "Chi Skills":
        return CHI_NAMES[index] if 0 <= index < len(CHI_NAMES) else f"Chi Skill #{index + 1:03d}"
    if collection == "Officer Cards":
        if 0 <= index < len(OFFICER_CARD_NAMES):
            return OFFICER_CARD_NAMES[index]
        if index == 99:
            return "Unknown / Unverified Officer Card #100"
        return f"Officer Card #{index + 1:03d}"
    if collection == "Orbs":
        return f"Orb #{index + 1:03d}"
    if collection == "Treasures":
        return TREASURE_NAMES[index] if 0 <= index < len(TREASURE_NAMES) else f"Treasure #{index + 1:02d}"
    return f"Entry {index}"

COLLECTION_SPECS = {
    "Weapons": {"kind": "u8", "ranges": ((OFF_WEAPON_FLAGS, WEAPON_FLAG_COUNT),), "verified": True},
    "Orbs": {"kind": "be16", "ranges": ORB_RANGES, "verified": True},
    "Chi Skills": {"kind": "be16", "ranges": CHI_RANGES, "verified": True},
    "Officer Cards": {"kind": "be16", "ranges": ((OFF_CARD_FLAGS, CARD_COUNT),), "verified": True},
    "Treasures": {"kind": "be16", "ranges": ((OFF_TREASURE_FLAGS, TREASURE_COUNT),), "verified": True},
}


def be16(buf: bytes | bytearray, off: int) -> int:
    return struct.unpack_from(">H", buf, off)[0]


def be32(buf: bytes | bytearray, off: int) -> int:
    return struct.unpack_from(">I", buf, off)[0]


def put_be16(buf: bytearray, off: int, value: int) -> None:
    struct.pack_into(">H", buf, off, value & 0xFFFF)


def put_be32(buf: bytearray, off: int, value: int) -> None:
    struct.pack_into(">I", buf, off, value & 0xFFFFFFFF)


def parse_int(text: str, lo: int, hi: int, label: str) -> int:
    t = text.strip()
    if not t:
        raise ValueError(f"{label} is empty")
    try:
        value = int(t, 0)
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid number: {text!r}") from exc
    if not lo <= value <= hi:
        raise ValueError(f"{label} must be between {lo} and {hi}")
    return value


def sfo_values_from_bytes(blob: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        if len(blob) < 20 or blob[:4] != b"\x00PSF":
            return out
        _magic, _ver, key_off, data_off, count = struct.unpack_from("<4sIIII", blob, 0)
        for i in range(count):
            eoff = 20 + i * 16
            if eoff + 16 > len(blob):
                break
            key_rel, _fmt, length, _max_len, data_rel = struct.unpack_from("<HHIII", blob, eoff)
            k0 = key_off + key_rel
            k1 = blob.find(b"\0", k0)
            if k1 < 0:
                continue
            key = blob[k0:k1].decode("utf-8", "replace")
            if key not in ("TITLE", "TITLE_ID"):
                continue
            start = data_off + data_rel
            raw = blob[start:start + length]
            out[key] = raw.rstrip(b"\0").decode("utf-8", "replace")
    except Exception:
        return {}
    return out

def sfo_title_from_bytes(blob: bytes) -> str | None:
    return sfo_values_from_bytes(blob).get("TITLE")


def hexdump(data: bytes | bytearray, base: int = 0, width: int = 16) -> str:
    lines = []
    for i in range(0, len(data), width):
        chunk = bytes(data[i:i + width])
        hx = " ".join(f"{x:02X}" for x in chunk)
        asc = "".join(chr(x) if 32 <= x < 127 else "." for x in chunk)
        lines.append(f"{base+i:08X}  {hx:<{width*3-1}}  |{asc}|")
    return "\n".join(lines)


@dataclass
class SaveSource:
    path: Path
    kind: str  # zip, app, folder
    app_member: str | None = None
    title: str | None = None
    title_id: str | None = None
    decrypted_marker: bool = False
    backup_path: Path | None = None


class WeaponMasterDB:
    def __init__(self, blob: bytes, source: Path | None = None) -> None:
        if len(blob) != WEAPON_DB_RECORD_COUNT * WEAPON_RECORD_SIZE:
            raise ValueError(
                f"00006.bin must be {WEAPON_DB_RECORD_COUNT * WEAPON_RECORD_SIZE:,} bytes "
                f"({WEAPON_DB_RECORD_COUNT} x {WEAPON_RECORD_SIZE}); got {len(blob):,}."
            )
        self.blob = blob
        self.source = source

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "WeaponMasterDB":
        p = Path(path)
        return cls(p.read_bytes(), p)

    def record(self, index: int) -> bytes:
        if not 0 <= index < WEAPON_DB_RECORD_COUNT:
            raise ValueError("Weapon database ID must be 0..298")
        b = index * WEAPON_RECORD_SIZE
        return self.blob[b:b + WEAPON_RECORD_SIZE]

    def label(self, index: int) -> str:
        return weapon_name(index)


class SaveDocument:
    def __init__(self) -> None:
        self.source: SaveSource | None = None
        self.original = b""
        self.data = bytearray()

    @property
    def dirty(self) -> bool:
        return bytes(self.data) != self.original

    @property
    def changed_bytes(self) -> int:
        if not self.original:
            return 0
        return sum(a != b for a, b in zip(self.original, self.data))

    def _make_backup(self, p: Path, kind: str, app_path: Path | None = None) -> Path | None:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            if kind == "zip":
                out = p.with_name(f"{p.stem}.backup-{stamp}{p.suffix}")
                shutil.copy2(p, out)
                return out
            if kind == "app":
                out = p.with_name(f"{p.name}.backup-{stamp}")
                shutil.copy2(p, out)
                return out
            if kind == "folder" and app_path is not None:
                out = app_path.with_name(f"{app_path.name}.backup-{stamp}")
                shutil.copy2(app_path, out)
                return out
        except Exception:
            return None
        return None

    def load(self, selected: str | os.PathLike[str], auto_backup: bool = True) -> None:
        p = Path(selected)
        backup: Path | None = None
        if p.is_dir():
            apps = list(p.rglob("APP.BIN"))
            if not apps:
                raise ValueError("No APP.BIN was found in that folder")
            app = apps[0]
            blob = app.read_bytes()
            title = None
            title_id = None
            sfo = next(iter(p.rglob("PARAM.SFO")), None)
            if sfo:
                vals = sfo_values_from_bytes(sfo.read_bytes())
                title = vals.get("TITLE")
                title_id = vals.get("TITLE_ID")
            marker = any(x.name == "~files_decrypted_by_pfdtool.txt" for x in p.rglob("*"))
            if auto_backup:
                backup = self._make_backup(p, "folder", app)
            self.source = SaveSource(p, "folder", str(app), title, title_id, marker, backup)
        elif p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p, "r") as zf:
                names = zf.namelist()
                candidates = [n for n in names if n.upper().endswith("/APP.BIN") or n.upper() == "APP.BIN"]
                if not candidates:
                    raise ValueError("ZIP does not contain APP.BIN")
                member = candidates[0]
                blob = zf.read(member)
                sfo_names = [n for n in names if n.upper().endswith("/PARAM.SFO") or n.upper() == "PARAM.SFO"]
                vals = sfo_values_from_bytes(zf.read(sfo_names[0])) if sfo_names else {}
                title = vals.get("TITLE")
                title_id = vals.get("TITLE_ID")
                marker = any(n.lower().endswith("~files_decrypted_by_pfdtool.txt") for n in names)
            if auto_backup:
                backup = self._make_backup(p, "zip")
            self.source = SaveSource(p, "zip", member, title, title_id, marker, backup)
        else:
            blob = p.read_bytes()
            if auto_backup:
                backup = self._make_backup(p, "app")
            self.source = SaveSource(p, "app", p.name, None, None, False, backup)

        if len(blob) != APP_SIZE:
            raise ValueError(
                f"Unexpected APP.BIN size: 0x{len(blob):X} ({len(blob):,} bytes).\n"
                f"BLES00825 is expected to be exactly 0x{APP_SIZE:X} bytes."
            )
        if self.source.title_id and self.source.title_id.upper() != EXPECTED_TITLE_ID:
            raise ValueError(
                f"Wrong PS3 title ID: {self.source.title_id}.\n"
                f"This editor is for {EXPECTED_TITLE_ID} only."
            )
        if self.source.title and "DYNASTY WARRIORS" not in self.source.title.upper():
            raise ValueError(f"Save title does not look like Dynasty Warriors: Strikeforce: {self.source.title}")

        self.original = bytes(blob)
        self.data = bytearray(blob)

    def restore_original(self) -> None:
        if not self.original:
            return
        self.data[:] = self.original

    def slot_base(self, slot: int) -> int:
        if not 0 <= slot < SLOT_COUNT:
            raise ValueError("Invalid slot")
        return slot * SLOT_SIZE

    def slot_active(self, slot: int) -> bool:
        b = self.slot_base(slot)
        region = self.data[b:b + SLOT_SIZE]
        if be32(self.data, b + OFF_GOLD) != 0:
            return True
        officer_region = region[OFF_OFFICER_XP:OFF_OFFICER_XP + OFFICER_COUNT * OFFICER_RECORD_SIZE]
        return any(officer_region)

    def gold(self, slot: int) -> int:
        return be32(self.data, self.slot_base(slot) + OFF_GOLD)

    def set_gold(self, slot: int, value: int) -> None:
        put_be32(self.data, self.slot_base(slot) + OFF_GOLD, value)

    # ---- selected officer runtime core -----------------------------------
    def selected_officer_id(self, slot: int) -> int:
        return self.data[self.slot_base(slot) + OFF_SELECTED_ID]

    def selected_officer_status(self, slot: int) -> int:
        return self.data[self.slot_base(slot) + OFF_SELECTED_STATUS]

    def selected_level(self, slot: int) -> int:
        return be16(self.data, self.slot_base(slot) + OFF_SELECTED_LEVEL)

    def set_selected_level(self, slot: int, value: int) -> None:
        if not 0 <= int(value) <= OFFICER_LEVEL_MAX:
            raise ValueError(f"Selected officer level must be 0..{OFFICER_LEVEL_MAX}")
        put_be16(self.data, self.slot_base(slot) + OFF_SELECTED_LEVEL, int(value))

    def selected_exp(self, slot: int) -> int:
        return be32(self.data, self.slot_base(slot) + OFF_SELECTED_EXP)

    def set_selected_exp(self, slot: int, value: int) -> None:
        if not 0 <= int(value) <= 0xFFFFFFFF:
            raise ValueError("Selected officer EXP must be 0..4294967295")
        put_be32(self.data, self.slot_base(slot) + OFF_SELECTED_EXP, int(value))

    def selected_xp(self, slot: int) -> list[int]:
        b = self.slot_base(slot) + OFF_SELECTED_XP
        return [be16(self.data, b + i * 2) for i in range(12)]

    def set_selected_xp(self, slot: int, values: list[int]) -> None:
        if len(values) != 12:
            raise ValueError("Selected officer proficiency/ability list must contain 12 values")
        b = self.slot_base(slot) + OFF_SELECTED_XP
        for i, v in enumerate(values):
            limit = OFFICER_PROFICIENCY_MAX if i < 6 else OFFICER_ABILITY_MAX
            if not 0 <= int(v) <= limit:
                raise ValueError(f"{OFFICER_STAT_LABELS[i]} must be 0..{limit}")
            put_be16(self.data, b + i * 2, int(v))

    # ---- persistent 42-officer records -----------------------------------
    def officer_record_base(self, slot: int, officer: int) -> int:
        if not 0 <= officer < OFFICER_COUNT:
            raise ValueError("Officer index out of range")
        return self.slot_base(slot) + OFF_OFFICER_RECORDS + officer * OFFICER_RECORD_SIZE

    def officer_id(self, slot: int, officer: int) -> int:
        return self.data[self.officer_record_base(slot, officer) + OFFICER_ID_REL]

    def officer_status(self, slot: int, officer: int) -> int:
        return self.data[self.officer_record_base(slot, officer) + OFFICER_STATUS_REL]

    def officer_level(self, slot: int, officer: int) -> int:
        return be16(self.data, self.officer_record_base(slot, officer) + OFFICER_LEVEL_REL)

    def set_officer_level(self, slot: int, officer: int, value: int) -> None:
        if not 0 <= int(value) <= OFFICER_LEVEL_MAX:
            raise ValueError(f"Officer level must be 0..{OFFICER_LEVEL_MAX}")
        put_be16(self.data, self.officer_record_base(slot, officer) + OFFICER_LEVEL_REL, int(value))

    def officer_exp(self, slot: int, officer: int) -> int:
        return be32(self.data, self.officer_record_base(slot, officer) + OFFICER_EXP_REL)

    def set_officer_exp(self, slot: int, officer: int, value: int) -> None:
        if not 0 <= int(value) <= 0xFFFFFFFF:
            raise ValueError("Officer EXP must be 0..4294967295")
        put_be32(self.data, self.officer_record_base(slot, officer) + OFFICER_EXP_REL, int(value))

    def officer_xp(self, slot: int, officer: int) -> list[int]:
        b = self.officer_record_base(slot, officer) + OFFICER_XP_REL
        return [be16(self.data, b + i * 2) for i in range(12)]

    def set_officer_xp(self, slot: int, officer: int, values: list[int]) -> None:
        if len(values) != 12:
            raise ValueError("Officer proficiency/ability list must contain 12 values")
        b = self.officer_record_base(slot, officer) + OFFICER_XP_REL
        for i, v in enumerate(values):
            limit = OFFICER_PROFICIENCY_MAX if i < 6 else OFFICER_ABILITY_MAX
            if not 0 <= int(v) <= limit:
                raise ValueError(f"{OFFICER_STAT_LABELS[i]} must be 0..{limit}")
            put_be16(self.data, b + i * 2, int(v))

    def officer_saved_weapon_ids(self, slot: int, officer: int) -> tuple[int, int]:
        r = self.officer_record_base(slot, officer)
        return be16(self.data, r + OFFICER_MAIN_WEAPON_REL), be16(self.data, r + OFFICER_SUB_WEAPON_REL)

    def set_officer_saved_weapon_ids(self, slot: int, officer: int, main_id: int, sub_id: int) -> None:
        r = self.officer_record_base(slot, officer)
        put_be16(self.data, r + OFFICER_MAIN_WEAPON_REL, int(main_id))
        put_be16(self.data, r + OFFICER_SUB_WEAPON_REL, int(sub_id))

    # Compatibility wrappers for old internal names.
    def selected_level_progress(self, slot: int) -> int:
        return self.selected_exp(slot) & 0xFFFF

    def set_selected_level_progress(self, slot: int, value: int) -> None:
        exp = self.selected_exp(slot)
        self.set_selected_exp(slot, (exp & 0xFFFF0000) | (int(value) & 0xFFFF))

    def officer_quick_level(self, slot: int, officer: int) -> int:
        return self.officer_level(slot, officer)

    def set_officer_quick_level(self, slot: int, officer: int, value: int) -> None:
        self.set_officer_level(slot, officer, value)

    def inventory_row(self, slot: int, index: int) -> tuple[int, int, int]:
        b = self.slot_base(slot)
        return (
            self.data[b + OFF_INVENTORY_IDS + index],
            self.data[b + OFF_INVENTORY_FLAGS + index],
            self.data[b + OFF_INVENTORY_QTY + index],
        )

    def set_inventory_row(self, slot: int, index: int, item_id: int, flag: int, qty: int) -> None:
        b = self.slot_base(slot)
        self.data[b + OFF_INVENTORY_IDS + index] = item_id & 0xFF
        self.data[b + OFF_INVENTORY_FLAGS + index] = flag & 0xFF
        self.data[b + OFF_INVENTORY_QTY + index] = qty & 0xFF

    def replace_inventory_material(self, slot: int, index: int, new_item_id: int, quantity: int | None = None) -> None:
        """Replace one real storehouse row and make the replacement usable.

        Material, owned flag, and quantity are parallel arrays. A replacement
        that leaves the row locked or at quantity 0 may not appear in game, so
        replacement explicitly marks the row owned. Quantity is caller-defined;
        if omitted, the existing non-zero quantity is preserved, otherwise 1 is
        used for a zero-quantity row.
        """
        if not 0 <= index < INVENTORY_SLOTS:
            raise ValueError("Inventory row must be 0..195")
        if not 0 <= new_item_id <= 0xFF:
            raise ValueError("Material must be 0..255")
        if quantity is not None and not 0 <= quantity <= 0xFF:
            raise ValueError("Quantity must be 0..255")
        b = self.slot_base(slot)
        id_off = b + OFF_INVENTORY_IDS + index
        flag_off = b + OFF_INVENTORY_FLAGS + index
        qty_off = b + OFF_INVENTORY_QTY + index
        self.data[id_off] = new_item_id & 0xFF
        self.data[flag_off] = 1
        if quantity is None:
            if self.data[qty_off] == 0:
                self.data[qty_off] = 1
        else:
            self.data[qty_off] = quantity & 0xFF

    def replace_all_inventory_material(self, slot: int, old_item_id: int, new_item_id: int, quantity: int | None = None) -> int:
        """Replace every matching real storehouse row in one save slot.

        Every replacement is marked owned. Existing non-zero quantities are
        preserved when quantity is None; zero quantities become 1.
        """
        if not 0 <= old_item_id <= 0xFF or not 0 <= new_item_id <= 0xFF:
            raise ValueError("Materials must be 0..255")
        if quantity is not None and not 0 <= quantity <= 0xFF:
            raise ValueError("Quantity must be 0..255")
        count = 0
        for index in range(INVENTORY_SLOTS):
            if self.inventory_row(slot, index)[0] == old_item_id:
                self.replace_inventory_material(slot, index, new_item_id, quantity)
                count += 1
        return count

    def apply_all_materials(self, slot: int, quantity: int = 99) -> None:
        b = self.slot_base(slot)
        # Preserve the PS3 patch's exact ID ordering but restrict ownership and
        # quantity writes to the 196 real storehouse rows.
        self.data[b + OFF_INVENTORY_ID_BLOCK:b + OFF_INVENTORY_ID_BLOCK + len(ALL_MATERIAL_IDS)] = ALL_MATERIAL_IDS
        self.data[b + OFF_INVENTORY_FLAGS:b + OFF_INVENTORY_FLAGS + INVENTORY_SLOTS] = b"\x01" * INVENTORY_SLOTS
        self.data[b + OFF_INVENTORY_QTY:b + OFF_INVENTORY_QTY + INVENTORY_SLOTS] = bytes([quantity & 0xFF]) * INVENTORY_SLOTS

    def max_storehouse(self, slot: int, value: int = 99) -> None:
        b = self.slot_base(slot)
        self.data[b + OFF_INVENTORY_QTY:b + OFF_INVENTORY_QTY + INVENTORY_SLOTS] = bytes([value & 0xFF]) * INVENTORY_SLOTS

    # ---- city facilities ---------------------------------------------------
    def city_levels(self, slot: int) -> list[int]:
        b = self.slot_base(slot) + OFF_CITY_LEVELS
        return list(self.data[b:b + CITY_FACILITY_COUNT])

    def city_exp(self, slot: int) -> list[int]:
        b = self.slot_base(slot) + OFF_CITY_EXP
        return [be16(self.data, b + i * 2) for i in range(CITY_FACILITY_COUNT)]

    def set_city_level(self, slot: int, index: int, value: int) -> None:
        if not 0 <= index < CITY_FACILITY_COUNT:
            raise ValueError("City facility index out of range")
        if not 0 <= value <= CITY_LEVEL_MAX:
            raise ValueError(f"City level must be 0..{CITY_LEVEL_MAX}")
        self.data[self.slot_base(slot) + OFF_CITY_LEVELS + index] = value & 0xFF

    def set_city_exp(self, slot: int, index: int, value: int) -> None:
        if not 0 <= index < CITY_FACILITY_COUNT:
            raise ValueError("City facility index out of range")
        if not 0 <= value <= 0xFFFF:
            raise ValueError("City EXP must be 0..65535")
        put_be16(self.data, self.slot_base(slot) + OFF_CITY_EXP + index * 2, value)

    def set_all_city(self, slot: int, level: int = CITY_LEVEL_MAX, exp: int | None = None) -> None:
        if not 0 <= level <= CITY_LEVEL_MAX:
            raise ValueError(f"City level must be 0..{CITY_LEVEL_MAX}")
        if exp is not None and not 0 <= exp <= 0xFFFF:
            raise ValueError("City EXP must be 0..65535")
        for i in range(CITY_FACILITY_COUNT):
            self.set_city_level(slot, i, level)
            if exp is not None:
                self.set_city_exp(slot, i, exp)

    # ---- collections -------------------------------------------------------
    def _collection_positions(self, slot: int, name: str) -> list[tuple[int, str]]:
        spec = COLLECTION_SPECS[name]
        b = self.slot_base(slot)
        out: list[tuple[int, str]] = []
        for off, count in spec["ranges"]:
            if spec["kind"] == "u8":
                out.extend((b + off + i, "u8") for i in range(count))
            else:
                out.extend((b + off + i * 2, "be16") for i in range(count))
        return out

    def collection_values(self, slot: int, name: str) -> list[int]:
        vals = []
        for off, kind in self._collection_positions(slot, name):
            vals.append(self.data[off] if kind == "u8" else be16(self.data, off))
        return vals

    def set_collection_value(self, slot: int, name: str, index: int, value: int) -> None:
        positions = self._collection_positions(slot, name)
        if not 0 <= index < len(positions):
            raise ValueError("Collection index out of range")
        off, kind = positions[index]
        if kind == "u8":
            self.data[off] = value & 0xFF
        else:
            put_be16(self.data, off, value)

    def set_collection_all(self, slot: int, name: str, value: int = 1) -> None:
        for off, kind in self._collection_positions(slot, name):
            if kind == "u8":
                self.data[off] = value & 0xFF
            else:
                put_be16(self.data, off, value)

    def prepare_collector_trophy(self, slot: int, name: str, missing_index: int) -> dict[str, int]:
        """Prepare a collector array for one final in-game acquisition/recheck.

        The mapped collection tables use exact owned value 1. Directly filling
        every entry can bypass the event that performs a trophy check, so prep
        normalizes the array and deliberately leaves one selected entry at 0.
        Weapons/Chi are completed by crafting the final item; Treasures are
        completed by satisfying/rechecking the chosen treasure condition in-game.
        """
        if name not in ("Weapons", "Chi Skills", "Treasures"):
            raise ValueError("Collector Trophy Prep supports Weapons, Chi Skills, and Treasures only")
        positions = self._collection_positions(slot, name)
        if not 0 <= missing_index < len(positions):
            raise ValueError("Selected collection index is out of range")
        before = self.collection_values(slot, name)
        self.set_collection_all(slot, name, 1)
        self.set_collection_value(slot, name, missing_index, 0)
        after = self.collection_values(slot, name)
        return {
            "total": len(after),
            "missing_index": missing_index,
            "changed": sum(a != b for a, b in zip(before, after)),
        }

    def collection_count(self, slot: int, name: str) -> tuple[int, int]:
        vals = self.collection_values(slot, name)
        return sum(v != 0 for v in vals), len(vals)

    # ---- story / request progression --------------------------------------
    def story_progress(self, slot: int) -> int:
        return self.data[self.slot_base(slot) + OFF_STORY_PROGRESS]

    def storyset_records(
        self,
        slot: int,
        category: int | None = None,
        chapters_only: bool = False,
    ) -> list[dict[str, int | str]]:
        """Return initialized StorySet records using the verified PS3 alignment."""
        b = self.slot_base(slot)
        out: list[dict[str, int | str]] = []
        for block_index, rel_base in enumerate(STORYSET_BLOCK_BASES):
            for rec_index in range(STORYSET_RECORDS_PER_BLOCK):
                off = b + rel_base + rec_index * STORYSET_RECORD_SIZE
                raw = self.data[off:off + STORYSET_RECORD_SIZE]
                if len(raw) != STORYSET_RECORD_SIZE or not any(raw):
                    continue
                stored_index = raw[STORYSET_RECORD_INDEX_REL]
                if stored_index == 0xFF:
                    continue
                rec_category = raw[STORYSET_CATEGORY_REL]
                chapter = raw[STORYSET_CHAPTER_REL]
                if category is not None and rec_category != category:
                    continue
                if chapters_only and not STORYSET_FIRST_CHAPTER <= chapter <= STORYSET_LAST_CHAPTER:
                    continue
                out.append({
                    "offset": off,
                    "block": block_index,
                    "faction": STORYSET_BLOCK_NAMES[block_index],
                    "record_index": rec_index,
                    "stored_index": stored_index,
                    "force": raw[STORYSET_FORCE_REL],
                    "chapter": chapter,
                    "category": rec_category,
                    "quest_id": raw[STORYSET_QUEST_ID_REL],
                    "link_id": raw[STORYSET_LINK_REL],
                    "state_a": raw[STORYSET_STATE_A_REL],
                    "state_b": raw[STORYSET_STATE_B_REL],
                    "state_c": raw[STORYSET_STATE_C_REL],
                    "state_d": raw[STORYSET_STATE_D_REL],
                })
        return out

    def request_records(self, slot: int) -> list[dict[str, int | str]]:
        return self.storyset_records(
            slot, category=STORYSET_CATEGORY_REQUEST, chapters_only=True
        )

    def chapter_story_records(self, slot: int) -> list[dict[str, int | str]]:
        return self.storyset_records(
            slot, category=STORYSET_CATEGORY_STORY, chapters_only=True
        )

    def chapter_story_count(self, slot: int) -> tuple[int, int]:
        rows = self.chapter_story_records(slot)
        return (
            sum(int(r["state_a"]) != 0 and int(r["state_b"]) != 0 for r in rows),
            len(rows),
        )

    def chapter_numbers(self, slot: int) -> list[int]:
        return sorted({int(r["chapter"]) for r in self.chapter_story_records(slot)})

    def unlock_all_chapters(self, slot: int) -> dict[str, int]:
        """Force all faction Chapters 1-6 into the postgame-access state.

        Correct v3.0 behavior:
        - global slot+0x0200 story-progress gate -> 0x07
        - real Story records in aligned StorySets: state A/B (+07/+08) -> 1
        - state C/D (+09/+0A) remain unchanged
        - Requests remain unchanged
        """
        rows = self.chapter_story_records(slot)
        progress_before = self.story_progress(slot)
        if not rows:
            return {"records": 0, "bytes_changed": 0, "progress_before": progress_before}

        changed = 0
        prog_off = self.slot_base(slot) + OFF_STORY_PROGRESS
        if self.data[prog_off] != STORY_PROGRESS_POSTGAME:
            self.data[prog_off] = STORY_PROGRESS_POSTGAME
            changed += 1

        for row in rows:
            off = int(row["offset"])
            for rel in (STORYSET_STATE_A_REL, STORYSET_STATE_B_REL):
                if self.data[off + rel] != 1:
                    self.data[off + rel] = 1
                    changed += 1

        return {
            "records": len(rows),
            "bytes_changed": changed,
            "progress_before": progress_before,
        }

    def request_count(self, slot: int) -> tuple[int, int]:
        rows = self.request_records(slot)
        return (
            sum(int(r["state_a"]) != 0 and int(r["state_b"]) != 0 for r in rows),
            len(rows),
        )

    def unlock_all_requests(self, slot: int) -> int:
        """Unlock Requests using the corrected +8-byte StorySet alignment."""
        rows = self.request_records(slot)
        for row in rows:
            off = int(row["offset"])
            self.data[off + STORYSET_STATE_A_REL] = 1
            self.data[off + STORYSET_STATE_B_REL] = 1
        return len(rows)

    def quest_records(self, slot: int) -> list[dict[str, int | str]]:
        """Return every initialized Chapter 1-6 Story or Request quest record."""
        return [
            row for row in self.storyset_records(slot, chapters_only=True)
            if int(row["category"]) in (STORYSET_CATEGORY_STORY, STORYSET_CATEGORY_REQUEST)
        ]

    def quest_count(self, slot: int) -> tuple[int, int]:
        rows = self.quest_records(slot)
        return (
            sum(int(r["state_a"]) != 0 and int(r["state_b"]) != 0 for r in rows),
            len(rows),
        )

    def unlock_quest_rows(self, slot: int, offsets: list[int], ensure_story_gate: bool = False) -> int:
        """Unlock selected quest records by setting only availability state A/B."""
        valid = {int(r["offset"]): r for r in self.quest_records(slot)}
        changed = 0
        has_story = False
        for off in offsets:
            row = valid.get(int(off))
            if not row:
                continue
            if int(row["category"]) == STORYSET_CATEGORY_STORY:
                has_story = True
            for rel in (STORYSET_STATE_A_REL, STORYSET_STATE_B_REL):
                if self.data[off + rel] != 1:
                    self.data[off + rel] = 1
                    changed += 1
        if ensure_story_gate and has_story:
            prog_off = self.slot_base(slot) + OFF_STORY_PROGRESS
            if self.data[prog_off] != STORY_PROGRESS_POSTGAME:
                self.data[prog_off] = STORY_PROGRESS_POSTGAME
                changed += 1
        return changed

    def unlock_all_quests(self, slot: int) -> dict[str, int]:
        """Unlock all 78 Story + 84 Request records while preserving completion state C/D."""
        story = self.unlock_all_chapters(slot)
        requests = self.request_records(slot)
        request_changed = 0
        for row in requests:
            off = int(row["offset"])
            for rel in (STORYSET_STATE_A_REL, STORYSET_STATE_B_REL):
                if self.data[off + rel] != 1:
                    self.data[off + rel] = 1
                    request_changed += 1
        return {
            "story_records": int(story["records"]),
            "request_records": len(requests),
            "bytes_changed": int(story["bytes_changed"]) + request_changed,
            "progress_before": int(story["progress_before"]),
        }

    def force_unlock_all_collections(self, slot: int, include_movies: bool = False, include_requests: bool = True, include_chapters: bool = True) -> None:
        # v4 REAL deliberately ignores include_movies. The old Movie mapping was
        # not PS3-verified strongly enough to keep as an editable write path.
        names = ["Weapons", "Orbs", "Chi Skills", "Officer Cards", "Treasures"]
        for name in names:
            self.set_collection_all(slot, name, 1)
        if include_chapters:
            self.unlock_all_chapters(slot)
        if include_requests:
            self.unlock_all_requests(slot)

    # ---- equipped weapon records -----------------------------------------
    def equipped_weapon_offset(self, slot: int, which: str) -> int:
        rel = OFF_EQUIPPED_MAIN if which == "Main" else OFF_EQUIPPED_SUB
        return self.slot_base(slot) + rel

    def equipped_weapon_record(self, slot: int, which: str) -> bytes:
        off = self.equipped_weapon_offset(slot, which)
        return bytes(self.data[off:off + WEAPON_RECORD_SIZE])

    def set_equipped_weapon_record(self, slot: int, which: str, record: bytes) -> None:
        if len(record) != WEAPON_RECORD_SIZE:
            raise ValueError("Weapon record must be exactly 100 bytes")
        off = self.equipped_weapon_offset(slot, which)
        self.data[off:off + WEAPON_RECORD_SIZE] = record

    def weapon_field(self, slot: int, which: str, rel: int, size: int = 2) -> int:
        off = self.equipped_weapon_offset(slot, which) + rel
        if size == 1:
            return self.data[off]
        if size == 2:
            return be16(self.data, off)
        raise ValueError("Unsupported weapon field size")

    def set_weapon_field(self, slot: int, which: str, rel: int, value: int, size: int = 2) -> None:
        off = self.equipped_weapon_offset(slot, which) + rel
        if size == 1:
            self.data[off] = value & 0xFF
        elif size == 2:
            put_be16(self.data, off, value)
        else:
            raise ValueError("Unsupported weapon field size")

    def weapon_id(self, slot: int, which: str) -> int:
        return self.weapon_field(slot, which, 0x00, 2)

    def validation_report(self) -> list[str]:
        lines = [f"APP.BIN size: 0x{len(self.data):X} ({len(self.data):,}) - {'OK' if len(self.data)==APP_SIZE else 'INVALID'}"]
        for slot in range(SLOT_COUNT):
            active = self.slot_active(slot)
            lines.append(f"Slot {slot+1}: {'active' if active else 'empty/placeholder'}; Gold={self.gold(slot):,}")
            if active:
                levels = self.city_levels(slot)
                exp = self.city_exp(slot)
                lines.append("  City: " + ", ".join(
                    f"{CITY_FACILITIES[i]} L{levels[i]} EXP {exp[i]}" for i in range(CITY_FACILITY_COUNT)
                ))
                for name in ("Weapons", "Orbs", "Chi Skills", "Officer Cards", "Treasures"):
                    have, total = self.collection_count(slot, name)
                    lines.append(f"  {name}: {have}/{total}")
                for which in ("Main", "Sub"):
                    wid = self.weapon_id(slot, which)
                    status = "OK" if wid < WEAPON_DB_RECORD_COUNT or wid == 0xFFFF else "OUT OF DB RANGE"
                    lines.append(f"  {which} weapon: 0x{wid:04X} ({wid}) - {status}")
        lines.append(f"Changed bytes vs original: {self.changed_bytes}")
        return lines

    def changed_runs(self, max_runs: int = 500) -> list[tuple[int, int]]:
        if not self.original:
            return []
        runs = []
        i = 0
        n = min(len(self.original), len(self.data))
        while i < n and len(runs) < max_runs:
            if self.original[i] == self.data[i]:
                i += 1
                continue
            j = i + 1
            while j < n and self.original[j] != self.data[j]:
                j += 1
            runs.append((i, j))
            i = j
        return runs

    def export(self, dest: str | os.PathLike[str]) -> Path:
        if self.source is None:
            raise ValueError("No save is loaded")
        if len(self.data) != APP_SIZE:
            raise ValueError("Working APP.BIN size changed; export blocked")
        dest = Path(dest)
        if self.source.kind == "zip":
            with zipfile.ZipFile(self.source.path, "r") as zin, zipfile.ZipFile(dest, "w") as zout:
                for info in zin.infolist():
                    payload = bytes(self.data) if info.filename == self.source.app_member else zin.read(info.filename)
                    zout.writestr(info, payload)
        else:
            dest.write_bytes(bytes(self.data))
        return dest


class BulkOfficerDialog(tk.Toplevel):
    """Set correct Level / EXP / proficiency / ability values for all officers."""
    def __init__(self, parent: tk.Misc, defaults: list[str]):
        super().__init__(parent)
        self.title("Set All 42 Officers - Custom Level + Stats")
        self.resizable(False, False);self.transient(parent)
        self.result: tuple[int, int, list[int]] | None = None
        self.vars=[tk.StringVar(value=str(defaults[i] if i < len(defaults) else 0)) for i in range(14)]
        body=ttk.Frame(self,padding=14);body.pack(fill="both",expand=True)
        ttk.Label(body,text=("Corrected persistent officer fields: Level 0-50, full 32-bit EXP, six weapon proficiencies 0-1000, and six ability stats 0-500."),wraplength=650,justify="left").grid(row=0,column=0,columnspan=4,sticky="w",pady=(0,10))
        labels=["Level","EXP"]+OFFICER_STAT_LABELS
        for i,label in enumerate(labels):
            r=1+i//2;c=(i%2)*2
            ttk.Label(body,text=label+":",width=22).grid(row=r,column=c,sticky="w",padx=(0,4),pady=4)
            ttk.Entry(body,textvariable=self.vars[i],width=14).grid(row=r,column=c+1,sticky="w",padx=(0,14),pady=4)
        nr=1+(len(labels)+1)//2
        q=ttk.Frame(body);q.grid(row=nr,column=0,columnspan=4,sticky="w",pady=(8,8))
        ttk.Button(q,text="Known-good Max",command=self._known_good_max).pack(side="left")
        ttk.Label(q,text="  Level 50 / EXP 50,000 / proficiency 1000 / abilities 500",foreground="#555").pack(side="left")
        b=ttk.Frame(body);b.grid(row=nr+1,column=0,columnspan=4,sticky="e")
        ttk.Button(b,text="Cancel",command=self.destroy).pack(side="right");ttk.Button(b,text="Apply",command=self._accept).pack(side="right",padx=(0,8))
        self.protocol("WM_DELETE_WINDOW",self.destroy);self.grab_set();self.after(10,lambda:self.focus_force())

    def _known_good_max(self)->None:
        vals=[OFFICER_LEVEL_MAX,OFFICER_QUICK_EXP]+[OFFICER_PROFICIENCY_MAX]*6+[OFFICER_ABILITY_MAX]*6
        for v,x in zip(self.vars,vals):v.set(str(x))

    def _accept(self)->None:
        try:
            level=parse_int(self.vars[0].get(),0,OFFICER_LEVEL_MAX,"Level");exp=parse_int(self.vars[1].get(),0,0xFFFFFFFF,"EXP");vals=[]
            for i,var in enumerate(self.vars[2:]):
                limit=OFFICER_PROFICIENCY_MAX if i<6 else OFFICER_ABILITY_MAX
                vals.append(parse_int(var.get(),0,limit,OFFICER_STAT_LABELS[i]))
        except ValueError as exc:messagebox.showerror("Invalid value",str(exc),parent=self);return
        self.result=(level,exp,vals);self.destroy()


class EditorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1240x820")
        self.minsize(1040, 700)
        self.doc = SaveDocument()
        self.weapon_db: WeaponMasterDB | None = None
        self.status_var = tk.StringVar(value="Open a decrypted BLES00825 save ZIP, folder, or APP.BIN.")
        self._build_ui()
        self._autoload_weapon_db()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---- UI construction --------------------------------------------------
    def _build_ui(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        top = ttk.Frame(self, padding=(10, 10, 10, 4))
        top.pack(fill="x")
        ttk.Button(top, text="Open Save", command=self.open_save).pack(side="left")
        ttk.Button(top, text="Export Edited Save", command=self.export_save).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Restore Original", command=self.restore_original).pack(side="left", padx=(8, 0))
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Label(top, text="Save slot:").pack(side="left")
        self.slot_combo = ttk.Combobox(top, state="readonly", width=14, values=["Slot 1", "Slot 2", "Slot 3"])
        self.slot_combo.current(0)
        self.slot_combo.pack(side="left", padx=(6, 0))
        self.slot_combo.bind("<<ComboboxSelected>>", self._slot_changed)
        ttk.Button(top, text="Validate", command=self.show_validation).pack(side="left", padx=(8, 0))

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=6)

        self.tab_overview = ttk.Frame(self.nb, padding=14)
        self.tab_officers = ttk.Frame(self.nb, padding=14)
        self.tab_weapons = ttk.Frame(self.nb, padding=14)
        self.tab_inventory = ttk.Frame(self.nb, padding=14)
        self.tab_city = ttk.Frame(self.nb, padding=14)
        self.tab_quests = ttk.Frame(self.nb, padding=14)
        self.tab_collections = ttk.Frame(self.nb, padding=14)
        self.nb.add(self.tab_overview, text="Overview")
        self.nb.add(self.tab_officers, text="Officers")
        self.nb.add(self.tab_weapons, text="Weapons")
        self.nb.add(self.tab_inventory, text="Items / Materials")
        self.nb.add(self.tab_city, text="City Upgrade")
        self.nb.add(self.tab_quests, text="All Quests")
        self.nb.add(self.tab_collections, text="Collections / Unlocks")

        self._build_overview()
        self._build_officers()
        self._build_weapons()
        self._build_inventory()
        self._build_city()
        self._build_quests()
        self._build_collections()

        status = ttk.Label(self, textvariable=self.status_var, anchor="w", relief="sunken", padding=(8, 5))
        status.pack(fill="x", side="bottom")
        self._set_controls(False)

    def _build_overview(self) -> None:
        f = self.tab_overview
        self.source_var = tk.StringVar(value="No save loaded")
        self.title_var = tk.StringVar(value="-")
        self.decrypt_var = tk.StringVar(value="-")
        self.backup_var = tk.StringVar(value="-")
        self.slot_state_var = tk.StringVar(value="-")
        self.format_var = tk.StringVar(value=FORMAT_LABEL)
        self.changed_var = tk.StringVar(value="0")
        self.gold_var = tk.StringVar(value="0")
        self.selected_level_var = tk.StringVar(value="0")
        self.selected_exp_var = tk.StringVar(value="0")
        self.selected_officer_var = tk.StringVar(value="-")

        info = ttk.LabelFrame(f, text="Save", padding=12)
        info.pack(fill="x")
        rows = [
            ("Source", self.source_var),
            ("Game title", self.title_var),
            ("PFDTool decrypted marker", self.decrypt_var),
            ("Automatic backup", self.backup_var),
            ("Current slot", self.slot_state_var),
            ("Verified format", self.format_var),
            ("Changed bytes", self.changed_var),
        ]
        for r, (label, var) in enumerate(rows):
            ttk.Label(info, text=label + ":", width=24).grid(row=r, column=0, sticky="w", pady=3)
            ttk.Label(info, textvariable=var).grid(row=r, column=1, sticky="w", pady=3)

        stats = ttk.LabelFrame(f, text="Core values", padding=12)
        stats.pack(fill="x", pady=(12, 0))
        ttk.Label(stats, text="Gold:").grid(row=0, column=0, sticky="w")
        ttk.Entry(stats, textvariable=self.gold_var, width=18).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Button(stats, text="Apply", command=self.apply_gold).grid(row=0, column=2, padx=4)
        ttk.Label(stats, text="Current officer:").grid(row=1, column=0, sticky="w", pady=(8,0))
        ttk.Label(stats, textvariable=self.selected_officer_var).grid(row=1, column=1, columnspan=2, sticky="w", padx=6, pady=(8,0))
        ttk.Label(stats, text="Current Level:").grid(row=2, column=0, sticky="w", pady=(8,0))
        ttk.Entry(stats, textvariable=self.selected_level_var, width=18).grid(row=2, column=1, sticky="w", padx=6, pady=(8,0))
        ttk.Label(stats, text="Current EXP:").grid(row=3, column=0, sticky="w", pady=(8,0))
        ttk.Entry(stats, textvariable=self.selected_exp_var, width=18).grid(row=3, column=1, sticky="w", padx=6, pady=(8,0))
        ttk.Button(stats, text="Apply Level + EXP", command=self.apply_selected_core).grid(row=2, column=2, rowspan=2, padx=4, pady=(8,0))

        actions = ttk.LabelFrame(f, text="Quick actions", padding=12)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Set All 42 Officers...", command=self.set_all_officers_custom).pack(side="left")
        ttk.Button(actions, text="Give All Weapons", command=lambda: self.unlock_collection("Weapons")).pack(side="left", padx=6)
        ttk.Button(actions, text="All Materials...", command=self.have_all_materials_custom).pack(side="left", padx=6)
        ttk.Button(actions, text="Unlock Orbs + Chi + Cards + Treasures", command=self.unlock_verified_collections).pack(side="left", padx=6)
        ttk.Button(actions, text="Unlock All Quests", command=self.unlock_all_quests).pack(side="left", padx=6)
        ttk.Button(actions, text="Unlock All Chapters", command=self.unlock_all_chapters).pack(side="left", padx=6)
        ttk.Button(actions, text="Unlock All Requests", command=self.unlock_all_requests).pack(side="left", padx=6)
        ttk.Button(actions, text="FORCE UNLOCK ALL", command=self.force_unlock_all).pack(side="left", padx=6)

        self.summary_tree = ttk.Treeview(f, columns=("name", "value"), show="headings", height=8)
        self.summary_tree.heading("name", text="Collection")
        self.summary_tree.heading("value", text="Owned / Total")
        self.summary_tree.column("name", width=240)
        self.summary_tree.column("value", width=140, anchor="center")
        self.summary_tree.pack(fill="x", pady=(12, 0))

    def _xp_editor(self, parent: ttk.Frame) -> list[tk.StringVar]:
        vars_: list[tk.StringVar] = []
        for i,label in enumerate(OFFICER_STAT_LABELS):
            row,col=divmod(i,4);cell=ttk.Frame(parent);cell.grid(row=row,column=col,sticky="ew",padx=5,pady=4);parent.columnconfigure(col,weight=1)
            ttk.Label(cell,text=label+":",width=19).pack(side="left");v=tk.StringVar(value="0");ttk.Entry(cell,textvariable=v,width=9).pack(side="left",fill="x",expand=True);vars_.append(v)
        return vars_

    def _build_officers(self) -> None:
        f = self.tab_officers

        # Internal selection/state. The visible UI intentionally uses names rather
        # than raw officer/status IDs.
        self.officer_selected_idx = 0
        self.officer_search_var = tk.StringVar(value="")
        self.officer_header_var = tk.StringVar(value=OFFICERS[0])
        self.officer_active_var = tk.StringVar(value="Active in game: -")
        self.officer_state_text_var = tk.StringVar(value="-")
        self.sync_active_officer_var = tk.BooleanVar(value=True)

        self.officer_level_var = tk.StringVar(value="0")
        self.officer_exp_var = tk.StringVar(value="0")
        self.officer_main_weapon_var = tk.StringVar(value="0")
        self.officer_sub_weapon_var = tk.StringVar(value="0")
        self.officer_main_weapon_name_var = tk.StringVar(value="-")
        self.officer_sub_weapon_name_var = tk.StringVar(value="-")

        # Runtime values stay available through the small "Active Runtime" dialog,
        # but are no longer mixed into the normal officer editor.
        self.selected_xp_vars = [tk.StringVar(value="0") for _ in OFFICER_STAT_LABELS]

        intro = ttk.Frame(f)
        intro.pack(fill="x", pady=(0, 8))
        ttk.Label(
            intro,
            text="Officer Editor",
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left")
        ttk.Label(
            intro,
            textvariable=self.officer_active_var,
        ).pack(side="right")

        sync = ttk.Frame(f)
        sync.pack(fill="x", pady=(0, 9))
        ttk.Checkbutton(
            sync,
            text="Keep the active in-game officer synchronized automatically",
            variable=self.sync_active_officer_var,
        ).pack(side="left")
        ttk.Button(
            sync,
            text="Active Runtime...",
            command=self.show_active_runtime_tools,
        ).pack(side="right")

        pan = ttk.Panedwindow(f, orient="horizontal")
        pan.pack(fill="both", expand=True)

        # Left: compact roster. No raw IDs and no wide horizontal scrolling.
        left = ttk.LabelFrame(pan, text="Choose Officer", padding=9)
        right = ttk.Frame(pan, padding=(12, 0, 0, 0))
        pan.add(left, weight=2)
        pan.add(right, weight=3)

        search_row = ttk.Frame(left)
        search_row.pack(fill="x", pady=(0, 7))
        ttk.Label(search_row, text="Search:").pack(side="left")
        search = ttk.Entry(search_row, textvariable=self.officer_search_var)
        search.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.officer_search_var.trace_add("write", self._officer_search_changed)

        cols = ("officer", "force", "level", "status")
        self.officer_tree = ttk.Treeview(
            left, columns=cols, show="headings", height=21, selectmode="browse"
        )
        for key, title, width, anchor in [
            ("officer", "Officer", 170, "w"),
            ("force", "Force", 65, "center"),
            ("level", "Level", 60, "center"),
            ("status", "Status", 105, "center"),
        ]:
            self.officer_tree.heading(key, text=title)
            self.officer_tree.column(key, width=width, anchor=anchor)
        y = ttk.Scrollbar(left, orient="vertical", command=self.officer_tree.yview)
        self.officer_tree.configure(yscrollcommand=y.set)
        self.officer_tree.pack(side="left", fill="both", expand=True)
        y.pack(side="right", fill="y")
        self.officer_tree.bind("<<TreeviewSelect>>", self._officer_tree_selected)
        self._officer_tree_refreshing = False

        # Right: selected officer, grouped by what a player actually wants to edit.
        head = ttk.Frame(right)
        head.pack(fill="x")
        ttk.Label(
            head,
            textvariable=self.officer_header_var,
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left")
        ttk.Label(
            head,
            textvariable=self.officer_state_text_var,
        ).pack(side="right")

        basics = ttk.LabelFrame(right, text="Level & Weapons", padding=10)
        basics.pack(fill="x", pady=(8, 0))
        basics.columnconfigure(1, weight=1)

        ttk.Label(basics, text="Level").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(basics, textvariable=self.officer_level_var, width=12).grid(
            row=0, column=1, sticky="w", padx=(8, 18), pady=4
        )
        ttk.Label(basics, text="EXP").grid(row=0, column=2, sticky="w", pady=4)
        ttk.Entry(basics, textvariable=self.officer_exp_var, width=16).grid(
            row=0, column=3, sticky="w", padx=(8, 0), pady=4
        )

        ttk.Label(basics, text="Main weapon").grid(row=1, column=0, sticky="w", pady=4)
        self.officer_main_weapon_combo = ttk.Combobox(
            basics,
            state="readonly",
            width=39,
            values=WEAPON_CHOICES,
            textvariable=self.officer_main_weapon_name_var,
        )
        self.officer_main_weapon_combo.grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=4
        )
        self.officer_main_weapon_combo.bind(
            "<<ComboboxSelected>>", self._officer_main_weapon_selected
        )

        ttk.Label(basics, text="Sub weapon").grid(row=2, column=0, sticky="w", pady=4)
        self.officer_sub_weapon_combo = ttk.Combobox(
            basics,
            state="readonly",
            width=39,
            values=WEAPON_CHOICES,
            textvariable=self.officer_sub_weapon_name_var,
        )
        self.officer_sub_weapon_combo.grid(
            row=2, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=4
        )
        self.officer_sub_weapon_combo.bind(
            "<<ComboboxSelected>>", self._officer_sub_weapon_selected
        )

        stats = ttk.LabelFrame(right, text="Stats", padding=10)
        stats.pack(fill="both", expand=True, pady=(8, 0))
        stats.columnconfigure(0, weight=1)
        stats.columnconfigure(1, weight=1)

        prof = ttk.LabelFrame(stats, text="Weapon Proficiency  (max 1000)", padding=8)
        abil = ttk.LabelFrame(stats, text="Abilities  (max 500)", padding=8)
        prof.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        abil.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        self.officer_xp_vars = []
        for i, name in enumerate(PROFICIENCY_NAMES):
            v = tk.StringVar(value="0")
            self.officer_xp_vars.append(v)
            ttk.Label(prof, text=name).grid(row=i, column=0, sticky="w", pady=3)
            ttk.Entry(prof, textvariable=v, width=10).grid(
                row=i, column=1, sticky="e", padx=(8, 0), pady=3
            )
            prof.columnconfigure(1, weight=1)

        for i, name in enumerate(OFFICER_ABILITY_NAMES):
            v = tk.StringVar(value="0")
            self.officer_xp_vars.append(v)
            ttk.Label(abil, text=name).grid(row=i, column=0, sticky="w", pady=3)
            ttk.Entry(abil, textvariable=v, width=10).grid(
                row=i, column=1, sticky="e", padx=(8, 0), pady=3
            )
            abil.columnconfigure(1, weight=1)

        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=(9, 0))
        ttk.Button(
            actions, text="Save Officer Changes", command=self.apply_officer
        ).pack(side="left")
        ttk.Button(
            actions, text="Max This Officer", command=self.max_current_officer_stats
        ).pack(side="left", padx=6)

        bulk = ttk.LabelFrame(right, text="All Officers", padding=8)
        bulk.pack(fill="x", pady=(9, 0))
        ttk.Label(
            bulk,
            text="Use these only when you want to change the full 42-officer roster.",
        ).pack(side="left")
        ttk.Button(
            bulk, text="Max All 42", command=self.repair_max_all_officers
        ).pack(side="right")
        ttk.Button(
            bulk, text="Custom All 42...", command=self.set_all_officers_custom
        ).pack(side="right", padx=6)

    def _build_weapons(self) -> None:
        f = self.tab_weapons
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Equipped weapon:").pack(side="left")
        self.weapon_which_combo = ttk.Combobox(top, state="readonly", width=10, values=["Main", "Sub"])
        self.weapon_which_combo.current(0)
        self.weapon_which_combo.pack(side="left", padx=6)
        self.weapon_which_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_weapon())
        self.weapon_db_var = tk.StringVar(value="Weapon templates: loading...")
        ttk.Label(top, textvariable=self.weapon_db_var).pack(side="right")

        core = ttk.LabelFrame(f, text="Equipped weapon", padding=10)
        core.pack(fill="x", pady=(10, 0))
        self.weapon_vars: dict[str, tk.StringVar] = {"id": tk.StringVar(value="0")}
        ttk.Label(core, text="Weapon:").grid(row=0, column=0, sticky="e", padx=5, pady=4)
        self.weapon_name_var = tk.StringVar(value="-")
        self.weapon_name_combo = ttk.Combobox(core, state="readonly", width=38, values=WEAPON_CHOICES)
        self.weapon_name_combo.grid(row=0, column=1, columnspan=2, sticky="ew", padx=5, pady=4)
        self.weapon_name_combo.bind("<<ComboboxSelected>>", self._weapon_name_selected)
        ttk.Button(core, text="Apply Selected Weapon", command=self.apply_weapon_template).grid(row=0, column=3, sticky="e", padx=5, pady=4)

        fields = [
            ("Standard Attack", "atk_s"), ("Power Attack", "atk_p"), ("Skill Attack", "atk_k"),
            ("Std Secondary", "sec_s"), ("Power Secondary", "sec_p"), ("Skill Secondary", "sec_k"),
            ("Critical", "crit"), ("Power Critical", "crit_hi"),
            ("Std Orb Slots", "orb_s"), ("Power Orb Slots", "orb_p"), ("Skill Orb Slots", "orb_k"),
        ]
        for i, (label, key) in enumerate(fields):
            r, c = divmod(i, 4)
            cell = ttk.Frame(core)
            cell.grid(row=r + 1, column=c, sticky="ew", padx=5, pady=4)
            core.columnconfigure(c, weight=1)
            ttk.Label(cell, text=label + ":", width=15).pack(side="left")
            v = tk.StringVar(value="0")
            ttk.Entry(cell, textvariable=v, width=10).pack(side="left", fill="x", expand=True)
            self.weapon_vars[key] = v
        ttk.Button(core, text="Apply Stats", command=self.apply_weapon_core).grid(row=4, column=3, sticky="e", padx=5, pady=(8, 2))

        split = ttk.Panedwindow(f, orient="horizontal")
        split.pack(fill="both", expand=True, pady=(10, 0))
        left = ttk.Frame(split)
        right = ttk.Frame(split, padding=(10, 0, 0, 0))
        split.add(left, weight=3)
        split.add(right, weight=2)

        ttk.Label(left, text="Weapon abilities", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.ability_tree = ttk.Treeview(left, columns=("style", "slot", "name", "level"), show="headings", height=12)
        for k, t, w in [("style","Style",90),("slot","Slot",55),("name","Ability",210),("level","Level",70)]:
            self.ability_tree.heading(k, text=t); self.ability_tree.column(k, width=w, anchor="center")
        self.ability_tree.pack(fill="both", expand=True)
        self.ability_tree.bind("<<TreeviewSelect>>", self._ability_selected)
        self.ability_row_ids: dict[str, int] = {}
        ab = ttk.Frame(left)
        ab.pack(fill="x", pady=(6, 0))
        self.ability_id_var = tk.StringVar(value=str(ABILITY_NONE))
        self.ability_name_var = tk.StringVar(value=ABILITY_NAMES[ABILITY_NONE])
        self.ability_level_var = tk.StringVar(value="0")
        ttk.Label(ab, text="Ability").pack(side="left")
        self.ability_name_combo = ttk.Combobox(ab, state="readonly", values=ABILITY_CHOICES, textvariable=self.ability_name_var, width=24)
        self.ability_name_combo.pack(side="left", padx=4)
        self.ability_name_combo.bind("<<ComboboxSelected>>", self._ability_name_selected)
        ttk.Label(ab, text="Level").pack(side="left")
        ttk.Entry(ab, textvariable=self.ability_level_var, width=8).pack(side="left", padx=4)
        ttk.Button(ab, text="Apply Selected Ability", command=self.apply_ability_row).pack(side="left", padx=6)

        ttk.Label(right, text="Crafting materials", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.craft_tree = ttk.Treeview(right, columns=("slot","name","qty"), show="headings", height=6)
        for k,t,w in [("slot","Slot",50),("name","Material",220),("qty","Qty",55)]:
            self.craft_tree.heading(k,text=t); self.craft_tree.column(k,width=w,anchor="center")
        self.craft_tree.pack(fill="x", pady=(4, 0))
        self.craft_tree.bind("<<TreeviewSelect>>", self._craft_selected)
        self.craft_row_ids: dict[str, int] = {}
        cr = ttk.Frame(right)
        cr.pack(fill="x", pady=(6, 0))
        self.craft_id_var = tk.StringVar(value="0")
        self.craft_qty_var = tk.StringVar(value="0")
        self.craft_name_combo = ttk.Combobox(cr, state="readonly", values=MATERIAL_CHOICES, width=27)
        self.craft_name_combo.pack(side="left", fill="x", expand=True)
        self.craft_name_combo.bind("<<ComboboxSelected>>", self._craft_name_selected)
        ttk.Label(cr,text="Qty").pack(side="left", padx=(6,0)); ttk.Entry(cr,textvariable=self.craft_qty_var,width=6).pack(side="left",padx=4)
        ttk.Button(cr,text="Apply",command=self.apply_craft_row).pack(side="left",padx=6)

        ttk.Separator(right).pack(fill="x", pady=10)
        ttk.Button(right, text="Restore this equipped weapon", command=self.restore_weapon_record).pack(fill="x")
        ttk.Button(right, text="Give All Weapon Ownership Flags", command=lambda: self.unlock_collection("Weapons")).pack(fill="x", pady=(6, 0))

    def _build_inventory(self) -> None:
        f = self.tab_inventory
        pan = ttk.Panedwindow(f, orient="horizontal")
        pan.pack(fill="both", expand=True)
        left = ttk.Frame(pan); right = ttk.Frame(pan, padding=(12,0,0,0))
        pan.add(left, weight=4); pan.add(right, weight=2)

        self.inv_tree = ttk.Treeview(left, columns=("idx","name","flag","qty"), show="headings", height=25)
        for key,title,width in [("idx","Slot",60),("name","Material",280),("flag","Owned",70),("qty","Qty",65)]:
            self.inv_tree.heading(key,text=title); self.inv_tree.column(key,width=width,anchor="center")
        sb=ttk.Scrollbar(left,orient="vertical",command=self.inv_tree.yview); self.inv_tree.configure(yscrollcommand=sb.set)
        self.inv_tree.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
        self.inv_tree.bind("<<TreeviewSelect>>",self._inventory_selected)

        ttk.Label(right,text="Selected storehouse row",font=("Segoe UI",10,"bold")).pack(anchor="w")
        self.inv_index_var=tk.StringVar(value="-"); self.inv_id_var=tk.StringVar(value="0"); self.inv_flag_var=tk.StringVar(value="0"); self.inv_qty_var=tk.StringVar(value="0"); self.inv_name_var=tk.StringVar(value="-")
        ttk.Label(right,text="Current material:").pack(anchor="w",pady=(9,2)); ttk.Label(right,textvariable=self.inv_name_var,wraplength=290).pack(anchor="w")
        ttk.Label(right,text="Replace with:").pack(anchor="w",pady=(9,2))
        self.inv_name_combo=ttk.Combobox(right,state="readonly",values=MATERIAL_CHOICES,width=35)
        self.inv_name_combo.pack(fill="x"); self.inv_name_combo.bind("<<ComboboxSelected>>",self._inventory_name_selected)
        ttk.Button(right,text="Replace Selected Material",command=self.replace_selected_material).pack(fill="x",pady=(6,0))
        ttk.Button(right,text="Replace All Matching Material...",command=self.replace_all_matching_material).pack(fill="x",pady=(6,0))
        for label,var in [("Slot",self.inv_index_var),("Owned flag",self.inv_flag_var),("Quantity",self.inv_qty_var)]:
            ttk.Label(right,text=label+":").pack(anchor="w",pady=(9,2)); ent=ttk.Entry(right,textvariable=var,width=18); ent.pack(anchor="w")
            if label=="Slot": ent.state(["disabled"])
        ttk.Button(right,text="Apply Owned / Quantity",command=self.apply_inventory_row).pack(anchor="w",pady=(12,0))
        ttk.Separator(right).pack(fill="x",pady=12)
        ttk.Button(right,text="Set all quantities...",command=self.set_storehouse_quantity_custom).pack(fill="x")
        ttk.Button(right,text="Have All Materials...",command=self.have_all_materials_custom).pack(fill="x",pady=(6,0))

    def _build_city(self) -> None:
        f = self.tab_city
        ttk.Label(
            f,
            text=(
                "City facility block (validated against BLES00825 PS3 APP.BIN saves): six level bytes at slot+0x1618 "
                "and six BE16 EXP values at slot+0x161E. Facility order follows the in-game city menu. "
                "Level 5 is the normal maximum; published cheat research uses 4990 EXP as a near-full gauge value."
            ),
            wraplength=1080, justify="left"
        ).pack(fill="x")

        pan = ttk.Panedwindow(f, orient="horizontal")
        pan.pack(fill="both", expand=True, pady=(12, 0))
        left = ttk.Frame(pan)
        right = ttk.Frame(pan, padding=(14, 0, 0, 0))
        pan.add(left, weight=4)
        pan.add(right, weight=2)

        self.city_tree = ttk.Treeview(left, columns=("idx", "facility", "level", "exp", "state"), show="headings", height=12)
        for key, title, width in [
            ("idx", "Index", 65), ("facility", "Facility", 220), ("level", "Level", 90),
            ("exp", "City EXP", 120), ("state", "Status", 170),
        ]:
            self.city_tree.heading(key, text=title)
            self.city_tree.column(key, width=width, anchor="center")
        self.city_tree.column("facility", anchor="w")
        self.city_tree.pack(fill="both", expand=True)
        self.city_tree.bind("<<TreeviewSelect>>", self._city_selected)

        self.city_index_var = tk.StringVar(value="-")
        self.city_level_var = tk.StringVar(value="0")
        self.city_exp_var = tk.StringVar(value="0")

        ttk.Label(right, text="Selected facility", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(right, text="Index:").pack(anchor="w", pady=(10, 2))
        ttk.Entry(right, textvariable=self.city_index_var, width=12, state="disabled").pack(anchor="w")
        ttk.Label(right, text="Level (0-5):").pack(anchor="w", pady=(10, 2))
        ttk.Entry(right, textvariable=self.city_level_var, width=12).pack(anchor="w")
        ttk.Label(right, text="City EXP (0-65535):").pack(anchor="w", pady=(10, 2))
        ttk.Entry(right, textvariable=self.city_exp_var, width=12).pack(anchor="w")
        ttk.Button(right, text="Apply Selected Facility", command=self.apply_city_row).pack(fill="x", pady=(12, 0))

        ttk.Separator(right).pack(fill="x", pady=14)
        ttk.Button(right, text="Set All to Level 5", command=self.set_all_city_level5).pack(fill="x")
        ttk.Button(right, text="Level 5 + 4990 EXP", command=self.set_all_city_near_full).pack(fill="x", pady=(6, 0))
        ttk.Button(right, text="Set All City Values...", command=self.set_all_city_custom).pack(fill="x", pady=(6, 0))
        ttk.Label(
            right,
            text=(
                "4990 EXP is intentionally exposed as the published near-full value rather than claiming an unverified "
                "exact full-gauge constant. After applying it, normal city post-battle processing can finish the gauge."
            ),
            wraplength=300, justify="left"
        ).pack(fill="x", pady=(12, 0))

    def _build_quests(self) -> None:
        f = self.tab_quests
        filters = ttk.Frame(f)
        filters.pack(fill="x")
        ttk.Label(filters, text="Type:").pack(side="left")
        self.quest_type_combo = ttk.Combobox(filters, state="readonly", width=12, values=["All", "Story", "Request"])
        self.quest_type_combo.current(0); self.quest_type_combo.pack(side="left", padx=(5, 12))
        ttk.Label(filters, text="Faction:").pack(side="left")
        self.quest_faction_combo = ttk.Combobox(filters, state="readonly", width=10, values=["All", *STORYSET_BLOCK_NAMES])
        self.quest_faction_combo.current(0); self.quest_faction_combo.pack(side="left", padx=(5, 12))
        ttk.Label(filters, text="Chapter:").pack(side="left")
        self.quest_chapter_combo = ttk.Combobox(filters, state="readonly", width=9, values=["All", "1", "2", "3", "4", "5", "6"])
        self.quest_chapter_combo.current(0); self.quest_chapter_combo.pack(side="left", padx=(5, 12))
        self.quest_count_var = tk.StringVar(value="-")
        ttk.Label(filters, textvariable=self.quest_count_var).pack(side="left", padx=8)
        ttk.Button(filters, text="Refresh", command=self.refresh_quests).pack(side="right")
        for combo in (self.quest_type_combo, self.quest_faction_combo, self.quest_chapter_combo):
            combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_quests())

        actions = ttk.Frame(f)
        actions.pack(fill="x", pady=(10, 8))
        ttk.Button(actions, text="Unlock Selected", command=self.unlock_selected_quests).pack(side="left")
        ttk.Button(actions, text="Unlock All Quests", command=self.unlock_all_quests).pack(side="left", padx=6)
        ttk.Button(actions, text="Unlock All Story", command=self.unlock_all_chapters).pack(side="left", padx=6)
        ttk.Button(actions, text="Unlock All Requests", command=self.unlock_all_requests).pack(side="left", padx=6)

        cols = ("faction", "type", "chapter", "quest", "available", "completed")
        self.quest_tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="extended", height=27)
        headers = [
            ("faction", "Faction", 90), ("type", "Type", 100), ("chapter", "Chapter", 80),
            ("quest", "Quest", 340), ("available", "Available", 90), ("completed", "Completed", 90),
        ]
        for key, label, width in headers:
            self.quest_tree.heading(key, text=label)
            self.quest_tree.column(key, width=width, anchor="center" if key != "quest" else "w")
        y = ttk.Scrollbar(f, orient="vertical", command=self.quest_tree.yview)
        self.quest_tree.configure(yscrollcommand=y.set)
        self.quest_tree.pack(side="left", fill="both", expand=True)
        y.pack(side="right", fill="y")
        self.quest_row_by_iid: dict[str, dict[str, int | str]] = {}

    def _build_collections(self) -> None:
        f=self.tab_collections
        top=ttk.Frame(f); top.pack(fill="x")
        ttk.Label(top,text="Collection:").pack(side="left")
        self.collection_combo=ttk.Combobox(top,state="readonly",width=24,values=list(COLLECTION_SPECS))
        self.collection_combo.current(0); self.collection_combo.pack(side="left",padx=6)
        self.collection_combo.bind("<<ComboboxSelected>>",lambda e:self.refresh_collection())
        self.collection_count_var=tk.StringVar(value="-"); ttk.Label(top,textvariable=self.collection_count_var).pack(side="left",padx=10)
        ttk.Button(top,text="Unlock All",command=self.unlock_current_collection).pack(side="right")
        ttk.Button(top,text="Clear All",command=self.clear_current_collection).pack(side="right",padx=6)

        pan=ttk.Panedwindow(f,orient="horizontal"); pan.pack(fill="both",expand=True,pady=(10,0))
        left=ttk.Frame(pan); right=ttk.Frame(pan,padding=(12,0,0,0)); pan.add(left,weight=4); pan.add(right,weight=2)
        self.collection_tree=ttk.Treeview(left,columns=("idx","name","force","state"),show="headings",height=25)
        for k,t,w in [("idx","#",55),("name","Name",300),("force","Force",80),("state","State",100)]:
            self.collection_tree.heading(k,text=t); self.collection_tree.column(k,width=w,anchor="center")
        self.collection_tree.column("name",anchor="w")
        self.collection_tree.pack(fill="both",expand=True); self.collection_tree.bind("<<TreeviewSelect>>",self._collection_selected)
        # Internal zero-based index is deliberately hidden; the user works with names and Owned/Missing state.
        self.collection_index_var=tk.StringVar(value="-")
        self.collection_selected_name_var=tk.StringVar(value="Select an entry")
        self.collection_selected_state_var=tk.StringVar(value="-")
        ttk.Label(right,text="Selected entry",font=("Segoe UI",10,"bold")).pack(anchor="w")
        ttk.Label(right,textvariable=self.collection_selected_name_var,wraplength=300).pack(anchor="w",pady=(10,2))
        ttk.Label(right,textvariable=self.collection_selected_state_var).pack(anchor="w",pady=(2,8))
        ttk.Button(right,text="Set Owned",command=lambda:self.set_selected_collection_state(True)).pack(fill="x",pady=(4,0))
        ttk.Button(right,text="Set Missing",command=lambda:self.set_selected_collection_state(False)).pack(fill="x",pady=(5,0))
        ttk.Separator(right).pack(fill="x",pady=12)
        ttk.Label(right,text="Collector Trophy Prep",font=("Segoe UI",10,"bold")).pack(anchor="w")
        ttk.Button(right,text="Leave Selected as Final Purchase",command=self.prepare_selected_collector_trophy).pack(fill="x",pady=(6,0))
        ttk.Button(right,text="Auto Prep Current Collection",command=self.prepare_auto_collector_trophy).pack(fill="x",pady=(5,0))
        ttk.Label(
            right,
            text=("Weapons / Chi / Treasures. Marks the rest as owned and leaves one named entry missing so the final in-game purchase or condition can trigger normally."),
            wraplength=310, justify="left"
        ).pack(fill="x",pady=(6,0))
        ttk.Separator(right).pack(fill="x",pady=12)
        ttk.Button(right,text="Unlock Weapons",command=lambda:self.unlock_collection("Weapons")).pack(fill="x")
        ttk.Button(right,text="Unlock Orbs",command=lambda:self.unlock_collection("Orbs")).pack(fill="x",pady=(5,0))
        ttk.Button(right,text="Unlock Chi Skills",command=lambda:self.unlock_collection("Chi Skills")).pack(fill="x",pady=(5,0))
        ttk.Button(right,text="Unlock Officer Cards",command=lambda:self.unlock_collection("Officer Cards")).pack(fill="x",pady=(5,0))
        ttk.Button(right,text="Unlock Treasures",command=lambda:self.unlock_collection("Treasures")).pack(fill="x",pady=(5,0))
        ttk.Button(right,text="Unlock All Quests",command=self.unlock_all_quests).pack(fill="x",pady=(5,0))
        ttk.Button(right,text="Unlock All Chapters",command=self.unlock_all_chapters).pack(fill="x",pady=(5,0))
        ttk.Button(right,text="Unlock All Requests",command=self.unlock_all_requests).pack(fill="x",pady=(5,0))
        ttk.Separator(right).pack(fill="x",pady=12)
        ttk.Button(right,text="FORCE UNLOCK ALL",command=self.force_unlock_all).pack(fill="x")

    def _build_advanced(self) -> None:
        f=self.tab_advanced
        top=ttk.Frame(f); top.pack(fill="x")
        ttk.Button(top,text="Validation Report",command=self.refresh_advanced_report).pack(side="left")
        ttk.Button(top,text="Show Changed Runs",command=self.show_changed_runs).pack(side="left",padx=6)
        ttk.Button(top,text="Restore Original",command=self.restore_original).pack(side="left",padx=6)

        rangebox=ttk.LabelFrame(f,text="Read-only hex range viewer",padding=8); rangebox.pack(fill="x",pady=(10,0))
        self.hex_off_var=tk.StringVar(value="0x0"); self.hex_len_var=tk.StringVar(value="0x100")
        ttk.Label(rangebox,text="File offset:").pack(side="left"); ttk.Entry(rangebox,textvariable=self.hex_off_var,width=12).pack(side="left",padx=5)
        ttk.Label(rangebox,text="Length:").pack(side="left"); ttk.Entry(rangebox,textvariable=self.hex_len_var,width=12).pack(side="left",padx=5)
        ttk.Button(rangebox,text="View",command=self.view_hex_range).pack(side="left",padx=6)

        self.advanced_text=tk.Text(f,wrap="none",font=("Consolas",9)); self.advanced_text.pack(fill="both",expand=True,pady=(10,0))

    def _build_info(self) -> None:
        text=(
            "Target\n  DYNASTY WARRIORS: Strikeforce - PS3 EU BLES00825\n\n"
            "Verified APP.BIN layout\n  File size: 0x48064\n  Slot size: 0x18000 x 3\n  Tail: 0x64\n\n"
            "Verified slot-relative fields\n"
            "  0x00D4 selected runtime record: ID/status, real Level at +0x06, full EXP at +0x08\n"
            "  0x00E0 current runtime: 6 weapon proficiencies + 6 ability stats (BE16)\n"
            "  0x012E main equipped weapon record (100 bytes)\n"
            "  0x0192 sub equipped weapon record (100 bytes)\n"
            "  0x03E2 weapon ownership flags (284 bytes)\n"
            "  0x061A / 0x068A orb ownership arrays\n"
            "  0x06E2 / 0x07D6 / 0x085E Chi ownership arrays\n"
            "  0x0872 officer-card ownership array\n"
            "  0x093A treasure ownership array\n"
            "  0x09B0 8-byte material prefix / 0x09B8 196 storehouse IDs\n  0x0A7C storehouse owned flags\n  0x0B44 storehouse quantities\n"
            "  0x1588 Gold (BE32)\n"
            "  0x1618 City facility levels (6 x u8; PS3 save-validated mapping)\n"
            "  0x161E City facility EXP (6 x BE16; PS3 save-validated mapping)\n"
            "  0x1874 + officer*0x40 persistent record: ID/status/Level/EXP; direct values begin at +0x0C\n"
            "  0x6458 / 0x6B60 / 0x7268 faction quest tables (12-byte records)\n\n"
            "Equipped weapon records\n"
            "  Their 100-byte layout is the same as LINKDATA entry 00006.bin. v2.5 exposes the mapped attack, critical, orb-slot, ability, crafting, and name fields. "
            "Loading 00006.bin allows a complete equipped record to be replaced safely from a master template.\n\n"
            "Collections\n"
            "  Weapon/Orb/Chi/Card/Treasure arrays were correlated against known original-game collection codes and confirmed to have the expected patterns in the supplied BLES00825 APP.BIN. "
            "Experimental Movie editing is intentionally not exposed in v4 REAL.\n\n"
            "City Upgrade\n"
            "  The six facility levels map to slot+0x1618 and the six facility EXP values to slot+0x161E. "
            "This mapping is also consistent with the original PSP layout, but v4 relies on the observed PS3 save behavior: the PSP city block follows the movie block, and the PS3 port shifts that late-save region by +0x200. "
            "Facility order: Blacksmith, Workshop, Academy, Exchange, Market, Storehouse. Published cheat research uses 4990 EXP as a near-full gauge value.\n\n"
            "Chapters / Requests\n"
            "  The three faction quest tables contain embedded chapter/category metadata. Category 0 is used for Story missions and category 1 for Noticeboard Requests. "
            "Unlock All Chapters sets slot+0x0200 to 0x07 and enables state A/B (+07/+08) on real Story records from StorySets at 0x6460/0x6B68/0x7270. State C/D are preserved.\n\n"
            "PFD / resigning\n"
            "  The editor modifies decrypted APP.BIN only. PARAM.PFD is not forged. Export the edited save, then re-encrypt/re-sign it with your normal PS3 save workflow before use on console.\n\n"
            "Safety\n"
            "  Source files are never overwritten by export. A timestamped backup is attempted automatically when a save is opened. Unknown bytes remain untouched unless a preset explicitly targets a mapped array."
        )
        box=tk.Text(self.tab_info,wrap="word",padx=8,pady=8); box.insert("1.0",text); box.configure(state="disabled"); box.pack(fill="both",expand=True)

    # ---- state / refresh ---------------------------------------------------
    def _set_controls(self, enabled: bool) -> None:
        state="normal" if enabled else "disabled"
        for tab in (self.tab_overview,self.tab_officers,self.tab_weapons,self.tab_inventory,self.tab_city,self.tab_quests,self.tab_collections):
            for w in tab.winfo_children(): self._state_recursive(w,state)
        if enabled:
            for combo in (self.slot_combo,self.weapon_which_combo,self.collection_combo): combo.configure(state="readonly")

    def _state_recursive(self, widget: tk.Widget, state: str) -> None:
        for child in widget.winfo_children(): self._state_recursive(child,state)
        if isinstance(widget,(ttk.Button,ttk.Entry,ttk.Combobox,ttk.Treeview,ttk.Checkbutton)):
            try:
                if isinstance(widget,ttk.Combobox) and state=="normal": widget.configure(state="readonly")
                else: widget.configure(state=state)
            except tk.TclError: pass

    def _slot(self) -> int: return self.slot_combo.current()
    def _weapon_which(self) -> str: return self.weapon_which_combo.get() or "Main"

    def _preset_xp(self, vars_: list[tk.StringVar], vals: list[int]) -> None:
        for var,v in zip(vars_,vals): var.set(str(v))

    def refresh_all(self) -> None:
        if not self.doc.source: return
        slot=self._slot(); src=self.doc.source
        self.source_var.set(str(src.path)); self.title_var.set(src.title or "BLES00825 / APP.BIN")
        self.decrypt_var.set("Yes" if src.decrypted_marker else "Not detected")
        self.backup_var.set(str(src.backup_path) if src.backup_path else "Backup could not be created")
        self.slot_state_var.set(f"Slot {slot+1} - {'active' if self.doc.slot_active(slot) else 'empty / placeholder'}")
        self.changed_var.set(str(self.doc.changed_bytes)); self.gold_var.set(str(self.doc.gold(slot)))
        sid=self.doc.selected_officer_id(slot);self.selected_officer_var.set(OFFICERS[sid] if 0 <= sid < OFFICER_COUNT else "Unknown officer")
        self.selected_level_var.set(str(self.doc.selected_level(slot)));self.selected_exp_var.set(str(self.doc.selected_exp(slot)))
        for var,val in zip(self.selected_xp_vars,self.doc.selected_xp(slot)): var.set(str(val))
        self.refresh_officer(); self.refresh_weapon(); self.refresh_inventory(); self.refresh_city(); self.refresh_quests(); self.refresh_collection(); self.refresh_summary(); self.refresh_advanced_report()
        self._update_title_dirty()

    def refresh_summary(self) -> None:
        for x in self.summary_tree.get_children(): self.summary_tree.delete(x)
        if not self.doc.source: return
        for name in COLLECTION_SPECS:
            have,total=self.doc.collection_count(self._slot(),name)
            self.summary_tree.insert("","end",values=(name,f"{have} / {total}"))
        levels = self.doc.city_levels(self._slot())
        exps = self.doc.city_exp(self._slot())
        city_maxed = sum(level >= CITY_LEVEL_MAX for level in levels)
        self.summary_tree.insert("","end",values=("City facilities",f"{city_maxed} / {CITY_FACILITY_COUNT} at Level {CITY_LEVEL_MAX}; EXP " + ", ".join(map(str, exps))))
        ch_have,ch_total=self.doc.chapter_story_count(self._slot())
        chapters=self.doc.chapter_numbers(self._slot())
        ch_label=(f"Ch. {chapters[0]}-{chapters[-1]}" if chapters else "no initialized table")
        self.summary_tree.insert("","end",values=("Chapters / Story",f"{ch_have} / {ch_total} unlocked ({ch_label})"))
        self.summary_tree.insert("","end",values=("Story progress gate",f"0x{self.doc.story_progress(self._slot()):02X} (postgame=0x07)"))
        have,total=self.doc.request_count(self._slot())
        self.summary_tree.insert("","end",values=("Requests",f"{have} / {total} unlocked"))
        q_have,q_total=self.doc.quest_count(self._slot())
        self.summary_tree.insert("","end",values=("All Quests",f"{q_have} / {q_total} available"))

    def refresh_quests(self) -> None:
        if not self.doc.source:return
        type_filter=self.quest_type_combo.get() or "All"
        faction_filter=self.quest_faction_combo.get() or "All"
        chapter_filter=self.quest_chapter_combo.get() or "All"
        for iid in self.quest_tree.get_children(): self.quest_tree.delete(iid)
        self.quest_row_by_iid.clear()
        shown=0
        for row in self.doc.quest_records(self._slot()):
            typ="Story" if int(row["category"])==STORYSET_CATEGORY_STORY else "Request"
            if type_filter != "All" and typ != type_filter: continue
            if faction_filter != "All" and row["faction"] != faction_filter: continue
            if chapter_filter != "All" and int(row["chapter"]) != int(chapter_filter): continue
            iid=f"quest_{int(row['offset']):06X}"
            self.quest_row_by_iid[iid]=row
            rec_no=int(row["record_index"])+1
            quest_label=f"{row['faction']} Chapter {int(row['chapter'])} {typ} {rec_no}"
            available="Yes" if int(row["state_a"]) or int(row["state_b"]) else "No"
            completed="Yes" if int(row["state_c"]) or int(row["state_d"]) else "No"
            self.quest_tree.insert("","end",iid=iid,values=(row["faction"],typ,row["chapter"],quest_label,available,completed))
            shown+=1
        have,total=self.doc.quest_count(self._slot())
        self.quest_count_var.set(f"Showing {shown} / {total}   |   Available {have} / {total}")

    def _officer_issue_labels(self, slot: int, idx: int) -> list[str]:
        vals = self.doc.officer_xp(slot, idx)
        issues: list[str] = []
        if self.doc.officer_level(slot, idx) > OFFICER_LEVEL_MAX:
            issues.append("level")
        if any(v > OFFICER_PROFICIENCY_MAX for v in vals[:6]):
            issues.append("proficiency")
        if any(v > OFFICER_ABILITY_MAX for v in vals[6:]):
            issues.append("abilities")
        return issues

    def _populate_officer_tree(self) -> None:
        if not self.doc.source:
            return
        slot = self._slot()
        query = self.officer_search_var.get().strip().lower()
        active_id = self.doc.selected_officer_id(slot)
        current = max(0, min(self.officer_selected_idx, OFFICER_COUNT - 1))

        self._officer_tree_refreshing = True
        try:
            for item in self.officer_tree.get_children():
                self.officer_tree.delete(item)

            selected_iid = None
            first_iid = None
            for i, name in enumerate(OFFICERS):
                force = OFFICER_FORCES[i]
                if query and query not in name.lower() and query not in force.lower():
                    continue
                issues = self._officer_issue_labels(slot, i)
                if issues:
                    status = "Review"
                elif i == active_id:
                    status = "Active"
                else:
                    status = "Normal"

                iid = f"officer_{i}"
                self.officer_tree.insert(
                    "", "end", iid=iid,
                    values=(name, force, self.doc.officer_level(slot, i), status)
                )
                if first_iid is None:
                    first_iid = iid
                if i == current:
                    selected_iid = iid

            if selected_iid is None and first_iid is not None:
                selected_iid = first_iid
                try:
                    self.officer_selected_idx = int(first_iid.split("_", 1)[1])
                except Exception:
                    self.officer_selected_idx = 0

            if selected_iid is not None:
                self.officer_tree.selection_set(selected_iid)
                self.officer_tree.focus(selected_iid)
                self.officer_tree.see(selected_iid)
        finally:
            self._officer_tree_refreshing = False

    def refresh_officer(self) -> None:
        if not self.doc.source:
            return
        slot = self._slot()
        idx = max(0, min(self.officer_selected_idx, OFFICER_COUNT - 1))
        self.officer_selected_idx = idx

        active_id = self.doc.selected_officer_id(slot)
        active_name = OFFICERS[active_id] if 0 <= active_id < OFFICER_COUNT else "Unknown officer"
        self.officer_active_var.set(f"Active in game: {active_name}")
        self.officer_header_var.set(f"{OFFICERS[idx]}  •  {OFFICER_FORCES[idx]}")

        issues = self._officer_issue_labels(slot, idx)
        if issues:
            state_text = "Needs review: " + ", ".join(issues)
        elif idx == active_id:
            state_text = "Active in game"
        else:
            state_text = "Ready"
        self.officer_state_text_var.set(state_text)

        self.officer_level_var.set(str(self.doc.officer_level(slot, idx)))
        self.officer_exp_var.set(str(self.doc.officer_exp(slot, idx)))

        main_id, sub_id = self.doc.officer_saved_weapon_ids(slot, idx)
        self.officer_main_weapon_var.set(str(main_id))
        self.officer_sub_weapon_var.set(str(sub_id))
        self.officer_main_weapon_name_var.set(weapon_name(main_id))
        self.officer_sub_weapon_name_var.set(weapon_name(sub_id))

        for v, x in zip(self.officer_xp_vars, self.doc.officer_xp(slot, idx)):
            v.set(str(x))

        self._populate_officer_tree()

    def refresh_weapon(self) -> None:
        if not self.doc.source:return
        slot=self._slot(); which=self._weapon_which()
        get=lambda rel,size=2:self.doc.weapon_field(slot,which,rel,size)
        vals={
            "id":get(0x00),"atk_s":get(0x16),"atk_p":get(0x18),"atk_k":get(0x1A),
            "sec_s":get(0x1C),"sec_p":get(0x1E),"sec_k":get(0x20),"crit_hi":get(0x22),
            "crit":get(0x24,1),"orb_s":get(0x25,1),"orb_p":get(0x26,1),"orb_k":get(0x27,1),
        }
        for k,x in vals.items():self.weapon_vars[k].set(str(x))
        wid=vals["id"]
        wname=weapon_name(wid)
        self.weapon_name_var.set(wname)
        self.weapon_name_combo.set(wname if wid in WEAPON_NAMES else "")
        for x in self.ability_tree.get_children():self.ability_tree.delete(x)
        self.ability_row_ids.clear()
        rec=self.doc.equipped_weapon_record(slot,which)
        styles=[("Standard",0x28,0x40),("Power",0x30,0x48),("Skill",0x38,0x50)]
        for style,ido,lvo in styles:
            for i in range(8):
                aid=rec[ido+i]; lvl=rec[lvo+i]; name=ABILITY_NAMES.get(aid,"Unknown ability")
                row=self.ability_tree.insert("","end",values=(style,i,name,lvl),tags=(str(ido+i),str(lvo+i)))
                self.ability_row_ids[row]=aid
        for x in self.craft_tree.get_children():self.craft_tree.delete(x)
        self.craft_row_ids.clear()
        for i in range(4):
            mid=rec[0x58+i]
            row=self.craft_tree.insert("","end",values=(i,material_name(mid),rec[0x5C+i]))
            self.craft_row_ids[row]=mid

    def refresh_inventory(self) -> None:
        if not self.doc.source:return
        selected=None; sel=self.inv_tree.selection()
        if sel:
            try:selected=int(self.inv_tree.item(sel[0],"values")[0])
            except Exception:pass
        for x in self.inv_tree.get_children():self.inv_tree.delete(x)
        for i in range(INVENTORY_SLOTS):
            iid,flag,qty=self.doc.inventory_row(self._slot(),i)
            row=self.inv_tree.insert("","end",values=(i,material_name(iid),flag,qty))
            if selected==i:self.inv_tree.selection_set(row);self.inv_tree.see(row)

    def refresh_city(self) -> None:
        if not self.doc.source:
            return
        selected = None
        sel = self.city_tree.selection()
        if sel:
            try:
                selected = int(self.city_tree.item(sel[0], "values")[0])
            except Exception:
                pass
        for item in self.city_tree.get_children():
            self.city_tree.delete(item)
        levels = self.doc.city_levels(self._slot())
        exps = self.doc.city_exp(self._slot())
        for i, name in enumerate(CITY_FACILITIES):
            level = levels[i]
            exp = exps[i]
            state = "Level 5" if level >= CITY_LEVEL_MAX else f"Level {level}"
            if level >= CITY_LEVEL_MAX and exp >= CITY_EXP_NEAR_FULL:
                state += " / near full"
            row = self.city_tree.insert("", "end", values=(i, name, level, exp, state))
            if selected == i:
                self.city_tree.selection_set(row)
                self.city_tree.see(row)

    def refresh_collection(self) -> None:
        if not self.doc.source:return
        name=self.collection_combo.get() or list(COLLECTION_SPECS)[0]
        vals=self.doc.collection_values(self._slot(),name); have=sum(v!=0 for v in vals)
        missing=[i for i,v in enumerate(vals) if v == 0]
        if name == "Officer Cards" and len(missing) == 1:
            mi=missing[0]
            mname=collection_entry_name(name,mi)
            mforce=officer_card_force(mi)
            self.collection_count_var.set(
                f"{have} / {len(vals)} owned — ONE LEFT: #{mi+1:03d} {mname} ({mforce})"
            )
        else:
            self.collection_count_var.set(f"{have} / {len(vals)} owned")
        selected=None;sel=self.collection_tree.selection()
        if sel:
            try:selected=self.collection_tree.index(sel[0])
            except Exception:pass
        # When exactly one Officer Card remains, always bring it into view.
        if name == "Officer Cards" and len(missing) == 1:
            selected=missing[0]
        for x in self.collection_tree.get_children():self.collection_tree.delete(x)
        for i,v in enumerate(vals):
            force=officer_card_force(i) if name == "Officer Cards" else ""
            state="Owned" if v else ("ONE LEFT" if name == "Officer Cards" and len(missing) == 1 and i == missing[0] else "Locked")
            row=self.collection_tree.insert("","end",values=(i+1,collection_entry_name(name,i),force,state))
            if selected==i:self.collection_tree.selection_set(row);self.collection_tree.see(row)

    def refresh_advanced_report(self) -> None:
        return

    def _autoload_weapon_db(self) -> None:
        try:
            base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
            candidate = base / "reference" / "00006.bin"
            if candidate.is_file():
                self.weapon_db = WeaponMasterDB.load(candidate)
                self.weapon_db_var.set("Weapon templates: ready")
        except Exception:
            self.weapon_db = None
            self.weapon_db_var.set("Weapon templates: unavailable")

    # ---- open / export -----------------------------------------------------
    def open_save(self) -> None:
        path=filedialog.askopenfilename(title="Open Strikeforce save",filetypes=[("PS3 save ZIP / APP.BIN","*.zip *.BIN *.bin"),("ZIP","*.zip"),("APP.BIN","*.BIN *.bin"),("All files","*.*")])
        if not path:
            if messagebox.askyesno("Open folder?","No file selected. Open a PS3 save folder instead?"):path=filedialog.askdirectory(title="Select BLES00825 save folder")
            if not path:return
        try:self.doc.load(path,auto_backup=True)
        except Exception as exc:messagebox.showerror("Open failed",str(exc));return
        self._set_controls(True);self.refresh_all();src=self.doc.source
        extra=f" Backup: {src.backup_path.name}" if src and src.backup_path else ""
        self.status_var.set(f"Loaded {src.path.name} - {len(self.doc.data):,} bytes.{extra}")

    def export_save(self) -> None:
        if not self.doc.source:return
        src=self.doc.source
        default=src.path.stem+"_edited.zip" if src.kind=="zip" else "APP_edited.BIN"
        types=[("ZIP","*.zip")] if src.kind=="zip" else [("BIN","*.BIN")]
        dest=filedialog.asksaveasfilename(title="Export edited save",initialfile=default,defaultextension=Path(default).suffix,filetypes=types)
        if not dest:return
        try:self.doc.export(dest)
        except Exception as exc:messagebox.showerror("Export failed",str(exc));return
        messagebox.showinfo("Export complete",f"Saved:\n{dest}\n\nAPP.BIN remains decrypted. Re-encrypt/re-sign the save before using it on PS3.")
        self.status_var.set(f"Exported {Path(dest).name}; source remains unchanged")

    def restore_original(self) -> None:
        if not self.doc.source:return
        if not messagebox.askyesno("Restore original","Discard all working edits and restore APP.BIN to the bytes that were loaded?"):return
        self.doc.restore_original();self.refresh_all();self.status_var.set("Working copy restored to original")

    # ---- core/officer actions --------------------------------------------
    def apply_gold(self) -> None:
        try:self.doc.set_gold(self._slot(),parse_int(self.gold_var.get(),0,0xFFFFFFFF,"Gold"))
        except ValueError as exc:messagebox.showerror("Invalid value",str(exc));return
        self._after_change("Gold updated")

    def apply_selected_core(self) -> None:
        try:
            level=parse_int(self.selected_level_var.get(),0,OFFICER_LEVEL_MAX,"Current officer level");exp=parse_int(self.selected_exp_var.get(),0,0xFFFFFFFF,"Current officer EXP");self.doc.set_selected_level(self._slot(),level);self.doc.set_selected_exp(self._slot(),exp)
        except ValueError as exc:messagebox.showerror("Invalid value",str(exc));return
        self._after_change(f"Current officer core updated: Level {level}, EXP {exp:,}")

    def apply_selected_level(self) -> None:self.apply_selected_core()

    def _xp_values_from(self,vars_:list[tk.StringVar])->list[int]:
        vals=[]
        for i,v in enumerate(vars_):
            limit=OFFICER_PROFICIENCY_MAX if i<6 else OFFICER_ABILITY_MAX;vals.append(parse_int(v.get(),0,limit,OFFICER_STAT_LABELS[i]))
        return vals

    def apply_selected_xp(self) -> None:
        try:
            self.doc.set_selected_xp(self._slot(), self._xp_values_from(self.selected_xp_vars))
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc))
            return
        self._after_change("Active in-game officer stats updated")

    def apply_active_runtime_all(self) -> None:
        try:
            level = parse_int(
                self.selected_level_var.get(), 0, OFFICER_LEVEL_MAX, "Active officer level"
            )
            exp = parse_int(
                self.selected_exp_var.get(), 0, 0xFFFFFFFF, "Active officer EXP"
            )
            vals = self._xp_values_from(self.selected_xp_vars)
            self.doc.set_selected_level(self._slot(), level)
            self.doc.set_selected_exp(self._slot(), exp)
            self.doc.set_selected_xp(self._slot(), vals)
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc))
            return
        self.refresh_all()
        self._after_change(f"Active in-game officer updated: Level {level}, EXP {exp:,}")

    def max_selected_stats(self) -> None:
        vals = [OFFICER_PROFICIENCY_MAX] * 6 + [OFFICER_ABILITY_MAX] * 6
        self.doc.set_selected_level(self._slot(), OFFICER_LEVEL_MAX)
        self.doc.set_selected_exp(self._slot(), OFFICER_QUICK_EXP)
        self.doc.set_selected_xp(self._slot(), vals)
        self.selected_level_var.set(str(OFFICER_LEVEL_MAX))
        self.selected_exp_var.set(str(OFFICER_QUICK_EXP))
        for v, x in zip(self.selected_xp_vars, vals):
            v.set(str(x))
        self.refresh_all()
        self._after_change(
            "Active in-game officer maxed: Level 50 / EXP 50,000 / proficiency 1000 / abilities 500"
        )

    def show_active_runtime_tools(self) -> None:
        if not self.doc.source:
            return
        slot = self._slot()
        active = self.doc.selected_officer_id(slot)
        active_name = OFFICERS[active] if 0 <= active < OFFICER_COUNT else "Unknown officer"

        win = tk.Toplevel(self)
        win.title("Active In-Game Officer")
        win.geometry("610x520")
        win.minsize(560, 470)
        win.transient(self)

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body, text=active_name, font=("Segoe UI", 13, "bold")
        ).pack(anchor="w")
        ttk.Label(
            body,
            text="These are the live values saved for the officer currently active in game. "
                 "Normal edits sync here automatically when the active officer matches.",
            wraplength=565,
            justify="left",
        ).pack(fill="x", pady=(3, 10))

        core = ttk.LabelFrame(body, text="Level", padding=9)
        core.pack(fill="x")
        ttk.Label(core, text="Level").grid(row=0, column=0, sticky="w")
        ttk.Entry(core, textvariable=self.selected_level_var, width=12).grid(
            row=0, column=1, padx=(8, 20)
        )
        ttk.Label(core, text="EXP").grid(row=0, column=2, sticky="w")
        ttk.Entry(core, textvariable=self.selected_exp_var, width=16).grid(
            row=0, column=3, padx=(8, 0)
        )

        stats = ttk.Frame(body)
        stats.pack(fill="both", expand=True, pady=(10, 0))
        stats.columnconfigure(0, weight=1)
        stats.columnconfigure(1, weight=1)

        prof = ttk.LabelFrame(stats, text="Weapon Proficiency", padding=8)
        abil = ttk.LabelFrame(stats, text="Abilities", padding=8)
        prof.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        abil.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        for i, name in enumerate(PROFICIENCY_NAMES):
            ttk.Label(prof, text=name).grid(row=i, column=0, sticky="w", pady=3)
            ttk.Entry(prof, textvariable=self.selected_xp_vars[i], width=10).grid(
                row=i, column=1, sticky="e", padx=(8, 0), pady=3
            )
            prof.columnconfigure(1, weight=1)

        for i, name in enumerate(OFFICER_ABILITY_NAMES):
            ttk.Label(abil, text=name).grid(row=i, column=0, sticky="w", pady=3)
            ttk.Entry(
                abil, textvariable=self.selected_xp_vars[6 + i], width=10
            ).grid(row=i, column=1, sticky="e", padx=(8, 0), pady=3)
            abil.columnconfigure(1, weight=1)

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(
            buttons, text="Apply Runtime Values", command=self.apply_active_runtime_all
        ).pack(side="left")
        ttk.Button(
            buttons, text="Max Active Runtime", command=self.max_selected_stats
        ).pack(side="left", padx=6)
        ttk.Button(buttons, text="Close", command=win.destroy).pack(side="right")

    def _sync_officer_values_to_runtime(
        self, idx: int, level: int, exp: int, vals: list[int]
    ) -> bool:
        """Mirror persistent values into the active runtime record when IDs match."""
        if self.doc.selected_officer_id(self._slot()) != idx:
            return False
        self.doc.set_selected_level(self._slot(), level)
        self.doc.set_selected_exp(self._slot(), exp)
        self.doc.set_selected_xp(self._slot(), vals)
        self.selected_level_var.set(str(level))
        self.selected_exp_var.set(str(exp))
        for v, x in zip(self.selected_xp_vars, vals):
            v.set(str(x))
        return True

    def sync_selected_officer_to_runtime(self) -> None:
        if not self.doc.source:
            return
        idx = self.officer_selected_idx
        active = self.doc.selected_officer_id(self._slot())
        if active != idx:
            active_name = OFFICERS[active] if 0 <= active < OFFICER_COUNT else "Unknown officer"
            messagebox.showinfo(
                "Active officer sync",
                f"{OFFICERS[idx]} is not the officer currently active in game.\n\n"
                f"Active officer: {active_name}",
            )
            return
        try:
            level = parse_int(
                self.officer_level_var.get(), 0, OFFICER_LEVEL_MAX, "Officer level"
            )
            exp = parse_int(
                self.officer_exp_var.get(), 0, 0xFFFFFFFF, "Officer EXP"
            )
            vals = self._xp_values_from(self.officer_xp_vars)
            self._sync_officer_values_to_runtime(idx, level, exp, vals)
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc))
            return
        self.refresh_all()
        self._after_change(f"Synchronized {OFFICERS[idx]} with the active in-game record")

    def apply_officer(self) -> None:
        idx = self.officer_selected_idx
        if not 0 <= idx < OFFICER_COUNT:
            return
        try:
            level = parse_int(
                self.officer_level_var.get(), 0, OFFICER_LEVEL_MAX, "Officer level"
            )
            exp = parse_int(
                self.officer_exp_var.get(), 0, 0xFFFFFFFF, "Officer EXP"
            )
            main_id = parse_int(
                self.officer_main_weapon_var.get(), 0, 0xFFFF, "Saved main weapon"
            )
            sub_id = parse_int(
                self.officer_sub_weapon_var.get(), 0, 0xFFFF, "Saved sub weapon"
            )
            vals = self._xp_values_from(self.officer_xp_vars)

            self.doc.set_officer_level(self._slot(), idx, level)
            self.doc.set_officer_exp(self._slot(), idx, exp)
            self.doc.set_officer_saved_weapon_ids(self._slot(), idx, main_id, sub_id)
            self.doc.set_officer_xp(self._slot(), idx, vals)

            synced = bool(self.sync_active_officer_var.get()) and self._sync_officer_values_to_runtime(
                idx, level, exp, vals
            )
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc))
            return

        self.refresh_all()
        self._after_change(
            f"Saved {OFFICERS[idx]} - Level {level}, EXP {exp:,}"
            + ("; active in-game values synchronized" if synced else "")
        )

    def max_current_officer_stats(self) -> None:
        idx = self.officer_selected_idx
        if not 0 <= idx < OFFICER_COUNT:
            return
        vals = [OFFICER_PROFICIENCY_MAX] * 6 + [OFFICER_ABILITY_MAX] * 6
        self.doc.set_officer_level(self._slot(), idx, OFFICER_LEVEL_MAX)
        self.doc.set_officer_exp(self._slot(), idx, OFFICER_QUICK_EXP)
        self.doc.set_officer_xp(self._slot(), idx, vals)
        synced = bool(self.sync_active_officer_var.get()) and self._sync_officer_values_to_runtime(
            idx, OFFICER_LEVEL_MAX, OFFICER_QUICK_EXP, vals
        )
        self.refresh_all()
        self._after_change(
            f"Maxed {OFFICERS[idx]} to Level 50 / EXP 50,000 / proficiency 1000 / abilities 500"
            + ("; active in-game values synchronized" if synced else "")
        )

    def repair_max_all_officers(self) -> None:
        if not self.doc.source:
            return
        bad = 0
        for i in range(OFFICER_COUNT):
            if self._officer_issue_labels(self._slot(), i):
                bad += 1
        if not messagebox.askyesno(
            "Max All 42 Officers",
            f"Set all {OFFICER_COUNT} officers to the known-good maximum?\n\n"
            "Level 50\nEXP 50,000\nAll weapon proficiencies = 1000\n"
            "All abilities = 500\n\n"
            f"Records needing review right now: {bad}\n\n"
            "Officer identity, status, and saved weapons are preserved.",
        ):
            return

        vals = [OFFICER_PROFICIENCY_MAX] * 6 + [OFFICER_ABILITY_MAX] * 6
        for i in range(OFFICER_COUNT):
            self.doc.set_officer_level(self._slot(), i, OFFICER_LEVEL_MAX)
            self.doc.set_officer_exp(self._slot(), i, OFFICER_QUICK_EXP)
            self.doc.set_officer_xp(self._slot(), i, vals)

        active = self.doc.selected_officer_id(self._slot())
        synced = False
        if (
            bool(self.sync_active_officer_var.get())
            and 0 <= active < OFFICER_COUNT
        ):
            synced = self._sync_officer_values_to_runtime(
                active, OFFICER_LEVEL_MAX, OFFICER_QUICK_EXP, vals
            )

        self.refresh_all()
        self._after_change(
            "Maxed all 42 officers"
            + ("; active in-game officer synchronized" if synced else "")
        )

    def set_all_officers_custom(self) -> None:
        if not self.doc.source:
            return
        defaults = [
            self.officer_level_var.get(),
            self.officer_exp_var.get(),
        ] + [v.get() for v in self.officer_xp_vars]
        dlg = BulkOfficerDialog(self, defaults)
        self.wait_window(dlg)
        if dlg.result is None:
            return
        level, exp, vals = dlg.result
        if not messagebox.askyesno(
            "Custom All 42 Officers",
            f"Apply these values to all {OFFICER_COUNT} officers in Slot {self._slot()+1}?\n\n"
            f"Level: {level}\nEXP: {exp:,}\n"
            f"Weapon proficiency: {', '.join(str(v) for v in vals[:6])}\n"
            f"Abilities: {', '.join(str(v) for v in vals[6:])}",
        ):
            return

        for i in range(OFFICER_COUNT):
            self.doc.set_officer_level(self._slot(), i, level)
            self.doc.set_officer_exp(self._slot(), i, exp)
            self.doc.set_officer_xp(self._slot(), i, vals)

        active = self.doc.selected_officer_id(self._slot())
        synced = False
        if bool(self.sync_active_officer_var.get()) and 0 <= active < OFFICER_COUNT:
            synced = self._sync_officer_values_to_runtime(active, level, exp, vals)

        self.refresh_all()
        self._after_change(
            "Applied custom values to all 42 officers"
            + ("; active in-game officer synchronized" if synced else "")
        )

    def _officer_main_weapon_selected(self, _event=None) -> None:
        name = self.officer_main_weapon_name_var.get().strip()
        if name in WEAPON_NAME_TO_ID:
            self.officer_main_weapon_var.set(str(WEAPON_NAME_TO_ID[name]))

    def _officer_sub_weapon_selected(self, _event=None) -> None:
        name = self.officer_sub_weapon_name_var.get().strip()
        if name in WEAPON_NAME_TO_ID:
            self.officer_sub_weapon_var.set(str(WEAPON_NAME_TO_ID[name]))

    # ---- weapon actions ---------------------------------------------------
    def load_weapon_db(self) -> None:
        path=filedialog.askopenfilename(title="Open extracted LINKDATA 00006.bin",filetypes=[("00006.bin / BIN","*.bin *.BIN"),("All files","*.*")])
        if not path:return
        try:self.weapon_db=WeaponMasterDB.load(path)
        except Exception as exc:messagebox.showerror("Weapon DB",str(exc));return
        self.weapon_db_var.set("Weapon templates: ready");self.refresh_weapon();self.status_var.set("Weapon templates loaded")

    def apply_weapon_core(self) -> None:
        try:
            vals={k:parse_int(v.get(),0,0xFFFF,k) for k,v in self.weapon_vars.items() if k not in ("crit","orb_s","orb_p","orb_k")}
            vals8={k:parse_int(self.weapon_vars[k].get(),0,0xFF,k) for k in ("crit","orb_s","orb_p","orb_k")}
            which=self._weapon_which();slot=self._slot()
            mapping={"id":0x00,"atk_s":0x16,"atk_p":0x18,"atk_k":0x1A,"sec_s":0x1C,"sec_p":0x1E,"sec_k":0x20,"crit_hi":0x22}
            for k,rel in mapping.items():self.doc.set_weapon_field(slot,which,rel,vals[k],2)
            for k,rel in {"crit":0x24,"orb_s":0x25,"orb_p":0x26,"orb_k":0x27}.items():self.doc.set_weapon_field(slot,which,rel,vals8[k],1)
        except ValueError as exc:messagebox.showerror("Invalid weapon value",str(exc));return
        self.refresh_weapon();self._after_change(f"{which} weapon core fields updated")

    def _weapon_name_selected(self, _event=None) -> None:
        name=self.weapon_name_combo.get().strip()
        if name not in WEAPON_NAME_TO_ID:return
        wid=WEAPON_NAME_TO_ID[name]
        self.weapon_vars["id"].set(str(wid)); self.weapon_name_var.set(name)

    def _ability_name_selected(self, _event=None) -> None:
        name=self.ability_name_var.get().strip()
        if name in ABILITY_NAME_TO_ID:self.ability_id_var.set(str(ABILITY_NAME_TO_ID[name]))

    def _craft_name_selected(self, _event=None) -> None:
        name=self.craft_name_combo.get().strip()
        if name in MATERIAL_NAME_TO_ID:self.craft_id_var.set(str(MATERIAL_NAME_TO_ID[name]))

    def _inventory_name_selected(self, _event=None) -> None:
        name=self.inv_name_combo.get().strip()
        if name in MATERIAL_NAME_TO_ID:self.status_var.set(f"Replacement selected: {name}")

    def _ability_selected(self,_event=None)->None:
        sel=self.ability_tree.selection()
        if not sel:return
        row=sel[0]; vals=self.ability_tree.item(row,"values"); aid=self.ability_row_ids.get(row,ABILITY_NONE)
        self.ability_id_var.set(str(aid)); self.ability_name_var.set(ABILITY_NAMES.get(aid,"Unknown ability")); self.ability_level_var.set(str(vals[3]))

    def apply_ability_row(self)->None:
        sel=self.ability_tree.selection()
        if not sel:messagebox.showerror("Ability","Select an ability row first");return
        vals=self.ability_tree.item(sel[0],"values");style=str(vals[0]);slotidx=int(vals[1]);base_id={"Standard":0x28,"Power":0x30,"Skill":0x38}[style];base_lv={"Standard":0x40,"Power":0x48,"Skill":0x50}[style]
        try:aid=parse_int(self.ability_id_var.get(),0,255,"Ability");lvl=parse_int(self.ability_level_var.get(),0,255,"Ability level")
        except ValueError as exc:messagebox.showerror("Invalid ability",str(exc));return
        self.doc.set_weapon_field(self._slot(),self._weapon_which(),base_id+slotidx,aid,1);self.doc.set_weapon_field(self._slot(),self._weapon_which(),base_lv+slotidx,lvl,1)
        self.refresh_weapon();self._after_change("Weapon ability updated")

    def _craft_selected(self,_event=None)->None:
        sel=self.craft_tree.selection()
        if not sel:return
        row=sel[0]; vals=self.craft_tree.item(row,"values"); mid=self.craft_row_ids.get(row,0)
        self.craft_id_var.set(str(mid));self.craft_qty_var.set(str(vals[2]));self.craft_name_combo.set(material_name(mid) if mid in MATERIAL_NAMES else "")

    def apply_craft_row(self)->None:
        sel=self.craft_tree.selection()
        if not sel:messagebox.showerror("Crafting","Select a crafting row first");return
        idx=int(self.craft_tree.item(sel[0],"values")[0])
        try:iid=parse_int(self.craft_id_var.get(),0,255,"Material");qty=parse_int(self.craft_qty_var.get(),0,255,"Material quantity")
        except ValueError as exc:messagebox.showerror("Invalid crafting value",str(exc));return
        self.doc.set_weapon_field(self._slot(),self._weapon_which(),0x58+idx,iid,1);self.doc.set_weapon_field(self._slot(),self._weapon_which(),0x5C+idx,qty,1)
        self.refresh_weapon();self._after_change("Weapon crafting row updated")

    def apply_weapon_template(self)->None:
        if not self.weapon_db:messagebox.showerror("Weapon templates","Bundled weapon templates are not available.");return
        name=self.weapon_name_combo.get().strip()
        if name not in WEAPON_NAME_TO_ID:messagebox.showerror("Weapon","Choose a named weapon first.");return
        wid=WEAPON_NAME_TO_ID[name]
        if wid>=WEAPON_DB_RECORD_COUNT:messagebox.showerror("Weapon","That weapon does not have a bundled template.");return
        if not messagebox.askyesno(
            "Replace equipped weapon",
            f"Replace the entire {self._weapon_which()} weapon with {name}?\n\n"
            "This resets customized attributes on that equipped weapon to the database defaults."
        ):
            return
        self.doc.set_equipped_weapon_record(self._slot(),self._weapon_which(),self.weapon_db.record(wid));self.refresh_weapon();self._after_change(f"Applied {name} weapon template")

    def restore_weapon_record(self)->None:
        if not self.doc.source:return
        off=self.doc.equipped_weapon_offset(self._slot(),self._weapon_which());orig=self.doc.original[off:off+WEAPON_RECORD_SIZE]
        self.doc.set_equipped_weapon_record(self._slot(),self._weapon_which(),orig);self.refresh_weapon();self._after_change("Equipped weapon record restored")

    # ---- inventory --------------------------------------------------------
    def _inventory_selected(self,_event=None)->None:
        sel=self.inv_tree.selection()
        if not sel:return
        idx=int(self.inv_tree.item(sel[0],"values")[0]);iid,flag,qty=self.doc.inventory_row(self._slot(),idx)
        self.inv_index_var.set(str(idx));self.inv_id_var.set(str(iid));self.inv_name_var.set(material_name(iid));self.inv_flag_var.set(str(flag));self.inv_qty_var.set(str(qty))
        self.inv_name_combo.set(MATERIAL_NAMES[iid] if iid in MATERIAL_NAMES else "")

    def apply_inventory_row(self)->None:
        try:
            idx=int(self.inv_index_var.get());iid=parse_int(self.inv_id_var.get(),0,255,"Material");flag=parse_int(self.inv_flag_var.get(),0,255,"Owned flag");qty=parse_int(self.inv_qty_var.get(),0,255,"Quantity")
            if not 0<=idx<INVENTORY_SLOTS:raise ValueError("Select an inventory row first")
            self.doc.set_inventory_row(self._slot(),idx,iid,flag,qty)
        except ValueError as exc:messagebox.showerror("Invalid value",str(exc));return
        self.refresh_inventory();self._after_change(f"Storehouse row {idx} updated")

    def replace_selected_material(self)->None:
        sel=self.inv_tree.selection()
        if not sel:
            messagebox.showerror("Replace material","Select a storehouse row first.");return
        choice=self.inv_name_combo.get().strip()
        if not choice:
            messagebox.showerror("Replace material","Choose the new material by name first.");return
        try:
            idx=int(self.inv_tree.item(sel[0],"values")[0])
            old_id,old_flag,old_qty=self.doc.inventory_row(self._slot(),idx)
            new_id=MATERIAL_NAME_TO_ID[choice]
        except Exception as exc:
            messagebox.showerror("Replace material",str(exc));return
        if old_id==new_id:
            self.status_var.set("Selected row already contains that material.");return
        old_name=material_name(old_id);new_name=material_name(new_id)
        qty=simpledialog.askinteger(
            "Replacement quantity",
            f"Quantity for {new_name} (0-255):",
            initialvalue=old_qty if old_qty>0 else 1, minvalue=0, maxvalue=255, parent=self)
        if qty is None:return
        if not messagebox.askyesno("Replace material",
            f"Replace storehouse row {idx}:\n\n{old_name}\n→ {new_name}\n\nNew row: Owned = 1, Quantity = {qty}"):
            return
        self.doc.replace_inventory_material(self._slot(),idx,new_id,qty)
        self.refresh_inventory()
        # Re-select the same logical row after rebuilding the tree.
        for item in self.inv_tree.get_children():
            if int(self.inv_tree.item(item,"values")[0])==idx:
                self.inv_tree.selection_set(item); self.inv_tree.see(item); break
        self._inventory_selected()
        self._after_change(f"Replaced {old_name} with {new_name} in storehouse row {idx}; quantity {qty}")

    def replace_all_matching_material(self)->None:
        win=tk.Toplevel(self)
        win.title("Replace All Matching Material")
        win.geometry("520x315")
        win.resizable(False,False)
        win.transient(self);win.grab_set()
        body=ttk.Frame(win,padding=14);body.pack(fill="both",expand=True)
        ttk.Label(body,text=f"Save Slot {self._slot()+1}: replace every matching storehouse material",font=("Segoe UI",10,"bold")).pack(anchor="w")
        ttk.Label(body,text="Current material:").pack(anchor="w",pady=(12,2))
        old_combo=ttk.Combobox(body,state="readonly",values=MATERIAL_CHOICES,width=58);old_combo.pack(fill="x")
        ttk.Label(body,text="New material:").pack(anchor="w",pady=(10,2))
        new_combo=ttk.Combobox(body,state="readonly",values=MATERIAL_CHOICES,width=58);new_combo.pack(fill="x")
        ttk.Label(body,text="Quantity for every replacement (0-255):").pack(anchor="w",pady=(10,2))
        qty_var=tk.StringVar(value="1")
        ttk.Entry(body,textvariable=qty_var,width=12).pack(anchor="w")
        # Preselect the current row as the source when possible.
        try:
            current_id=int(self.inv_id_var.get())
            if current_id in MATERIAL_NAMES: old_combo.set(MATERIAL_NAMES[current_id])
        except Exception:
            pass
        ttk.Label(body,text="Ownership flags and quantities are preserved for every replaced row.",wraplength=475).pack(anchor="w",pady=(10,0))
        buttons=ttk.Frame(body);buttons.pack(fill="x",pady=(12,0))
        def apply_replace():
            try:
                old_text=old_combo.get().strip();new_text=new_combo.get().strip()
                if not old_text or not new_text: raise ValueError("Choose both the current and new material.")
                old_id=MATERIAL_NAME_TO_ID[old_text];new_id=MATERIAL_NAME_TO_ID[new_text]
                qty=parse_int(qty_var.get(),0,255,"Quantity")
                if old_id==new_id: raise ValueError("Current and new material are the same.")
            except Exception as exc:
                messagebox.showerror("Replace materials",str(exc),parent=win);return
            matches=sum(1 for i in range(INVENTORY_SLOTS) if self.doc.inventory_row(self._slot(),i)[0]==old_id)
            if matches==0:
                messagebox.showinfo("Replace materials",f"No {material_name(old_id)} entries were found in this slot.",parent=win);return
            if not messagebox.askyesno("Replace materials",f"Replace {matches} storehouse row(s) containing {material_name(old_id)} with {material_name(new_id)}?\n\nEvery replacement will be Owned = 1, Quantity = {qty}.",parent=win):return
            count=self.doc.replace_all_inventory_material(self._slot(),old_id,new_id,qty)
            win.destroy();self.refresh_inventory();self._after_change(f"Replaced {count} {material_name(old_id)} row(s) with {material_name(new_id)}; quantity {qty}")
        ttk.Button(buttons,text="Replace All Matches",command=apply_replace).pack(side="left")
        ttk.Button(buttons,text="Cancel",command=win.destroy).pack(side="right")

    def set_storehouse_quantity_custom(self)->None:
        value=simpledialog.askinteger("Set all quantities",
            f"Quantity for all {INVENTORY_SLOTS} storehouse rows in Slot {self._slot()+1}:",
            parent=self,minvalue=0,maxvalue=255,initialvalue=99)
        if value is None:return
        self.doc.max_storehouse(self._slot(),value);self.refresh_inventory();self._after_change(f"All storehouse quantities set to {value}")

    def have_all_materials_custom(self)->None:
        value=simpledialog.askinteger("Have All Materials",
            "Quantity to assign to every material (0-255):",
            parent=self,minvalue=0,maxvalue=255,initialvalue=99)
        if value is None:return
        if not messagebox.askyesno("Have All Materials",
            f"Apply the verified BLES00825 all-material preset and set every material quantity to {value}?"):return
        self.doc.apply_all_materials(self._slot(),value);self.refresh_inventory();self._after_change(f"All Materials preset applied with quantity {value}")

    # ---- city facilities --------------------------------------------------
    def _city_selected(self, _event=None) -> None:
        sel = self.city_tree.selection()
        if not sel:
            return
        vals = self.city_tree.item(sel[0], "values")
        self.city_index_var.set(str(vals[0]))
        self.city_level_var.set(str(vals[2]))
        self.city_exp_var.set(str(vals[3]))

    def apply_city_row(self) -> None:
        try:
            idx = int(self.city_index_var.get())
            level = parse_int(self.city_level_var.get(), 0, CITY_LEVEL_MAX, "City level")
            exp = parse_int(self.city_exp_var.get(), 0, 0xFFFF, "City EXP")
            if not 0 <= idx < CITY_FACILITY_COUNT:
                raise ValueError("Select a city facility first")
            self.doc.set_city_level(self._slot(), idx, level)
            self.doc.set_city_exp(self._slot(), idx, exp)
        except ValueError as exc:
            messagebox.showerror("City Upgrade", str(exc))
            return
        self.refresh_city()
        self._after_change(f"{CITY_FACILITIES[idx]} set to Level {level}, EXP {exp}")

    def set_all_city_level5(self) -> None:
        if not messagebox.askyesno(
            "City Upgrade",
            f"Set all {CITY_FACILITY_COUNT} city facility level bytes in Slot {self._slot()+1} to Level {CITY_LEVEL_MAX}?\n\n"
            "Existing city EXP values will be preserved."
        ):
            return
        self.doc.set_all_city(self._slot(), CITY_LEVEL_MAX, None)
        self.refresh_city()
        self._after_change("All city facilities set to Level 5")

    def set_all_city_near_full(self) -> None:
        if not messagebox.askyesno(
            "City Upgrade - Level 5 + 4990 EXP",
            f"Set all {CITY_FACILITY_COUNT} facilities in Slot {self._slot()+1} to Level {CITY_LEVEL_MAX} and City EXP {CITY_EXP_NEAR_FULL}?\n\n"
            "The 4990 value comes from the original game's published CITY EXP cheat and is intended as a near-full gauge value."
        ):
            return
        self.doc.set_all_city(self._slot(), CITY_LEVEL_MAX, CITY_EXP_NEAR_FULL)
        self.refresh_city()
        self._after_change(f"All city facilities set to Level 5 + {CITY_EXP_NEAR_FULL} EXP")

    def set_all_city_custom(self) -> None:
        level = simpledialog.askinteger(
            "Set All City Values", "Level for all six facilities (0-5):",
            parent=self, minvalue=0, maxvalue=CITY_LEVEL_MAX, initialvalue=CITY_LEVEL_MAX
        )
        if level is None:
            return
        exp = simpledialog.askinteger(
            "Set All City Values", "City EXP for all six facilities (0-65535):",
            parent=self, minvalue=0, maxvalue=0xFFFF, initialvalue=CITY_EXP_NEAR_FULL
        )
        if exp is None:
            return
        self.doc.set_all_city(self._slot(), level, exp)
        self.refresh_city()
        self._after_change(f"All city facilities set to Level {level}, EXP {exp}")

    # ---- collections ------------------------------------------------------
    def _collection_selected(self,_event=None)->None:
        sel=self.collection_tree.selection()
        if not sel:return
        row=sel[0]
        idx=self.collection_tree.index(row)
        vals=self.collection_tree.item(row,"values")
        self.collection_index_var.set(str(idx))
        self.collection_selected_name_var.set(str(vals[1]))
        force=str(vals[2]).strip()
        state=str(vals[3])
        self.collection_selected_state_var.set((force + " · " if force else "") + state)

    def set_selected_collection_state(self, owned: bool)->None:
        try:idx=int(self.collection_index_var.get())
        except Exception:
            messagebox.showerror("Collection","Select a named collection entry first.");return
        name=self.collection_combo.get()
        vals=self.doc.collection_values(self._slot(),name)
        if not 0 <= idx < len(vals):
            messagebox.showerror("Collection","Select a valid collection entry first.");return
        self.doc.set_collection_value(self._slot(),name,idx,1 if owned else 0)
        item=collection_entry_name(name,idx)
        self.refresh_collection();self.refresh_summary();self._after_change(f"{item} set to {'Owned' if owned else 'Missing'}")

    def _collector_trophy_missing_index(self, name: str) -> int:
        vals = self.doc.collection_values(self._slot(), name)
        known_limit = len(vals)
        if name == "Chi Skills":
            known_limit = min(known_limit, len(CHI_NAMES))
        elif name == "Weapons":
            # Prefer a named personal/generic weapon when possible.
            named = [i for i in range(len(vals)) if i in WEAPON_NAMES]
            for i in named:
                if vals[i] == 0:
                    return i
            return named[0] if named else 0
        elif name == "Treasures":
            # Prefer a missing Treasure whose condition is easy for the editor
            # to infer as already satisfiable/recheckable from this save.
            rows = [self.doc.inventory_row(self._slot(), i) for i in range(INVENTORY_SLOTS)]
            stored_rows = sum(flag != 0 and qty != 0 for _, flag, qty in rows)
            officer_max = max(self.doc.officer_quick_level(self._slot(), i) for i in range(OFFICER_COUNT))
            city_ready = all(v >= 5 for v in self.doc.city_levels(self._slot())) and all(v >= 4990 for v in self.doc.city_exp(self._slot()))
            preferred = []
            if stored_rows >= 100:
                preferred.append(8)   # Awards of Valor
            if officer_max >= 50:
                preferred.append(10)  # He's Jade
            if city_ready:
                preferred.append(17)  # Bronze Pheasant
            if self.doc.story_progress(self._slot()) >= 7:
                preferred.extend([4, 0])  # Book of Illusions / Grand Histories
            # Avoid online-only Treasures for Auto Prep unless no other choice.
            preferred.extend(i for i in range(len(vals)) if i not in (18, 19))
            preferred.extend([18, 19])
            seen = set()
            for i in preferred:
                if i in seen or not 0 <= i < len(vals):
                    continue
                seen.add(i)
                if vals[i] == 0:
                    return i
            return 8 if len(vals) > 8 else 0
        for i in range(known_limit):
            if vals[i] == 0:
                return i
        return 0

    def _prepare_collector_trophy(self, name: str, idx: int) -> None:
        if name not in ("Weapons", "Chi Skills", "Treasures"):
            messagebox.showerror(
                "Collector Trophy Prep",
                "Select Weapons, Chi Skills, or Treasures first."
            )
            return
        vals = self.doc.collection_values(self._slot(), name)
        if not 0 <= idx < len(vals):
            messagebox.showerror("Collector Trophy Prep", "Select a valid collection entry first.")
            return
        item = collection_entry_name(name, idx)
        if name == "Weapons":
            trophy = "Weapon Collector"
            action = f"MAKE {item} at the Blacksmith"
            detail = "The final in-game crafting transaction should run the game's normal collector-trophy check."
            steps = [f"Go to the Blacksmith.", f"MAKE {item} normally."]
        elif name == "Chi Skills":
            trophy = "Chi Collector"
            action = f"MAKE {item} at the Academy"
            detail = "The final in-game crafting transaction should run the game's normal collector-trophy check."
            steps = [f"Go to the Academy.", f"MAKE {item} normally."]
        else:
            trophy = "Treasure Collector"
            condition = TREASURE_CONDITIONS[idx] if 0 <= idx < len(TREASURE_CONDITIONS) else "Satisfy this Treasure's normal unlock condition"
            action = condition
            detail = ("Treasures are normally awarded when their underlying condition is satisfied or rechecked, often after completing a quest. "
                      "The selected Treasure remains 0 so the game, not the editor, performs the final Treasure acquisition.")
            steps = [f"Satisfy/recheck: {condition}.", "Complete the required quest/battle if that condition calls for one."]

        if not messagebox.askyesno(
            f"Prepare {trophy}",
            f"Prepare Slot {self._slot()+1} for the {trophy} trophy?\n\n"
            f"All other named entries in {name} will be marked Owned. This one stays Missing:\n"
            f"  #{idx+1:03d}: {item}\n\n"
            f"Final in-game action: {action}.\n\n"
            f"{detail}\n\nKeep a backup of your original save."
        ):
            return
        result = self.doc.prepare_collector_trophy(self._slot(), name, idx)
        self.refresh_collection(); self.refresh_summary(); self.refresh_advanced_report()
        self._after_change(
            f"{trophy} prep: {item} left missing; {result['changed']} entries changed"
        )
        numbered = "\n".join(f"{n+3}. {text}" for n, text in enumerate(steps))
        messagebox.showinfo(
            f"{trophy} Prep Ready",
            f"Final missing entry: #{idx+1:03d} {item}\n\n"
            f"1. Export/save APP.BIN.\n"
            f"2. Load it in Dynasty Warriors: Strikeforce.\n"
            f"{numbered}\n"
            f"{len(steps)+3}. Let the game finish its normal save/update.\n\n"
            "Do not press Unlock All on this collection after Trophy Prep, or the final missing trigger will be removed."
        )

    def prepare_selected_collector_trophy(self) -> None:
        name = self.collection_combo.get()
        try:
            idx = int(self.collection_index_var.get())
        except Exception:
            messagebox.showerror("Collector Trophy Prep", "Select the final Weapon, Chi, or Treasure entry in the list first.")
            return
        self._prepare_collector_trophy(name, idx)

    def prepare_auto_collector_trophy(self) -> None:
        name = self.collection_combo.get()
        if name not in ("Weapons", "Chi Skills", "Treasures"):
            messagebox.showerror("Collector Trophy Prep", "Select Weapons, Chi Skills, or Treasures first.")
            return
        idx = self._collector_trophy_missing_index(name)
        self._prepare_collector_trophy(name, idx)

    def unlock_collection(self,name:str)->None:
        spec=COLLECTION_SPECS[name]
        if not spec["verified"]:
            if not messagebox.askyesno("Experimental collection",f"{name} is not fully verified for the PS3 port. Apply value 1 to all entries anyway?"):return
        else:
            if not messagebox.askyesno("Unlock collection",f"Mark every {name} entry in Slot {self._slot()+1} as Owned?"):return
        self.doc.set_collection_all(self._slot(),name,1);self.refresh_collection();self.refresh_summary();self._after_change(f"Unlocked all {name}")

    def unlock_current_collection(self)->None:self.unlock_collection(self.collection_combo.get())

    def clear_current_collection(self)->None:
        name=self.collection_combo.get()
        if not messagebox.askyesno("Clear collection",f"Mark every {name} entry in this slot as Missing? This can relock content."):return
        self.doc.set_collection_all(self._slot(),name,0);self.refresh_collection();self.refresh_summary();self._after_change(f"Cleared {name}")

    def unlock_selected_quests(self)->None:
        if not self.doc.source:
            return
        sel = self.quest_tree.selection()
        if not sel:
            messagebox.showwarning("No quest selected", "Select one or more quest rows first.")
            return
        rows = [self.quest_row_by_iid[i] for i in sel if i in self.quest_row_by_iid]
        offsets = [int(r["offset"]) for r in rows]
        story_count = sum(int(r["category"]) == STORYSET_CATEGORY_STORY for r in rows)
        request_count = len(rows) - story_count
        if not messagebox.askyesno(
            "Unlock Selected Quests",
            f"Unlock {len(rows)} selected quest record(s) in Slot {self._slot()+1}?\n\n"
            f"Story: {story_count}\nRequests: {request_count}\n\n"
            "Availability state A/B will be set to 1. State C/D is preserved. "
            "If Story quests are selected, the global story gate will also be set to postgame 0x07."
        ):
            return
        changed = self.doc.unlock_quest_rows(self._slot(), offsets, ensure_story_gate=True)
        self.refresh_quests(); self.refresh_summary(); self.refresh_advanced_report()
        self._after_change(f"Unlocked {len(rows)} selected quest record(s); {changed} byte(s) changed")

    def unlock_all_quests(self)->None:
        slot = self._slot()
        rows = self.doc.quest_records(slot)
        if not rows:
            messagebox.showwarning("No initialized quests", f"Slot {slot + 1} has no initialized StorySet quest records.")
            return
        have, total = self.doc.quest_count(slot)
        story_total = len(self.doc.chapter_story_records(slot))
        request_total = len(self.doc.request_records(slot))
        if not messagebox.askyesno(
            "Unlock All Quests",
            f"Unlock every initialized quest in Slot {slot + 1}?\n\n"
            f"Story quests: {story_total}\nNoticeboard Requests: {request_total}\n"
            f"Currently available: {have} / {total}\n\n"
            "This sets Story/Request availability state A/B to 1 and the global Story gate to 0x07. "
            "Completion/runtime state C/D is preserved exactly."
        ):
            return
        result = self.doc.unlock_all_quests(slot)
        self.refresh_quests(); self.refresh_summary(); self.refresh_advanced_report()
        self._after_change(
            f"Unlocked all {int(result['story_records']) + int(result['request_records'])} quests; "
            f"{int(result['bytes_changed'])} byte(s) changed"
        )

    def unlock_all_chapters(self)->None:
        slot = self._slot()
        rows = self.doc.chapter_story_records(slot)
        if not rows:
            messagebox.showwarning(
                "No initialized Chapters",
                f"Slot {slot + 1} does not contain initialized PS3 StorySet tables."
            )
            return
        progress = self.doc.story_progress(slot)
        have, total = self.doc.chapter_story_count(slot)
        if not messagebox.askyesno(
            "Unlock All Chapters - v3.0 corrected",
            f"Force Wei / Wu / Shu Chapters 1-6 available in Slot {slot + 1}?\n\n"
            f"Current global story progress: 0x{progress:02X}\n"
            f"Postgame target: 0x{STORY_PROGRESS_POSTGAME:02X}\n"
            f"Story availability state A/B: {have} / {total}\n\n"
            "APP(8).BIN confirmed why v2.9 failed: the global chapter-map gate "
            "was still 0x05. The completed reference save uses 0x07. The older "
            "editor was also parsing every StorySet 8 bytes too early.\n\n"
            "v3.0 fixes both. State C/D and Requests are left unchanged."
        ):
            return
        result = self.doc.unlock_all_chapters(slot)
        self.refresh_summary(); self.refresh_advanced_report()
        self._after_change(
            f"Unlocked Chapters: progress 0x{int(result['progress_before']):02X}->"
            f"0x{STORY_PROGRESS_POSTGAME:02X}; {int(result['records'])} Story records; "
            f"{int(result['bytes_changed'])} byte(s) changed"
        )

    def unlock_all_requests(self)->None:
        slot = self._slot()
        rows = self.doc.request_records(slot)
        if not rows:
            messagebox.showwarning("No initialized Requests", f"Slot {slot + 1} has no initialized Request records.")
            return
        before = sum(int(r["state_a"]) != 0 and int(r["state_b"]) != 0 for r in rows)
        if not messagebox.askyesno(
            "Unlock All Requests - v3.0 corrected",
            f"Unlock all {len(rows)} Noticeboard Requests in Slot {slot + 1}?\n\n"
            f"Currently available: {before} / {len(rows)}\n\n"
            "Uses the corrected StorySet alignment and sets state A/B (+07/+08). "
            "State C/D are preserved."
        ):
            return
        count = self.doc.unlock_all_requests(slot)
        self.refresh_summary(); self.refresh_advanced_report()
        self._after_change(f"Unlocked all {count} Noticeboard Requests")

    def force_unlock_all(self)->None:
        slot = self._slot()
        msg = (
            f"FORCE UNLOCK ALL mapped collections in Slot {slot + 1}?\n\n"
            "This writes the unlocked value 1 to:\n"
            "  - all 284 Weapon entries\n"
            "  - all 94 Orb entries\n"
            "  - all 174 Chi Skill entries\n"
            "  - all 100 Officer Card entries\n"
            "  - all 20 Treasure entries\n"
            "  - postgame chapter-map gate + all aligned Wei/Wu/Shu Story availability states\n"
            "  - all aligned Noticeboard Request availability states\n\n"
            "Materials, quantities, gold, officer stats, and equipped weapons are NOT changed."
        )
        if not messagebox.askyesno("FORCE UNLOCK ALL", msg):
            return
        self.doc.force_unlock_all_collections(slot, include_movies=False, include_requests=True, include_chapters=True)
        self.refresh_collection(); self.refresh_summary()
        self._after_change("FORCE UNLOCK ALL applied to mapped collections")

    def unlock_verified_collections(self)->None:
        if not messagebox.askyesno("Unlock collections","Unlock all Orbs, Chi Skills, Officer Cards, and Treasures in the current slot?\n\nWeapons are left separate because the Give All Weapons button handles them independently."):return
        for name in ("Orbs","Chi Skills","Officer Cards","Treasures"):self.doc.set_collection_all(self._slot(),name,1)
        self.refresh_collection();self.refresh_summary();self._after_change("Unlocked Orbs, Chi Skills, Officer Cards, and Treasures")

    # ---- advanced ---------------------------------------------------------
    def show_validation(self)->None:
        if not self.doc.source:return
        messagebox.showinfo("Validation","\n".join(self.doc.validation_report()))

    def show_changed_runs(self)->None:
        if not self.doc.source:return
        runs=self.doc.changed_runs();lines=[f"Changed runs: {len(runs)}",""]
        for a,b in runs:lines.append(f"0x{a:06X} - 0x{b-1:06X}  ({b-a} byte{'s' if b-a!=1 else ''})")
        if len(runs)>=500:lines.append("\nOutput capped at 500 runs.")
        self.advanced_text.delete("1.0","end");self.advanced_text.insert("1.0","\n".join(lines))

    def view_hex_range(self)->None:
        if not self.doc.source:return
        try:off=parse_int(self.hex_off_var.get(),0,APP_SIZE-1,"Offset");length=parse_int(self.hex_len_var.get(),1,0x4000,"Length")
        except ValueError as exc:messagebox.showerror("Hex range",str(exc));return
        end=min(APP_SIZE,off+length);self.advanced_text.delete("1.0","end");self.advanced_text.insert("1.0",hexdump(self.doc.data[off:end],off))

    # ---- events / status --------------------------------------------------
    def _slot_changed(self,_event=None)->None:self.refresh_all()

    def _officer_search_changed(self, *_args) -> None:
        if self.doc.source:
            old_idx = self.officer_selected_idx
            self._populate_officer_tree()
            if self.officer_selected_idx != old_idx:
                self.refresh_officer()

    def _officer_changed(self,_event=None)->None:
        # Kept for compatibility with older internal calls.
        if self.doc.source:self.refresh_officer()

    def _officer_tree_selected(self,_event=None)->None:
        if not self.doc.source or getattr(self, "_officer_tree_refreshing", False):
            return
        sel = self.officer_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if not iid.startswith("officer_"):
            return
        try:
            idx = int(iid.split("_", 1)[1])
        except (TypeError, ValueError):
            return
        if 0 <= idx < OFFICER_COUNT and idx != self.officer_selected_idx:
            self.officer_selected_idx = idx
            self.refresh_officer()

    def _after_change(self,msg:str)->None:
        self.changed_var.set(str(self.doc.changed_bytes));self._update_title_dirty();self.refresh_summary();self.status_var.set(f"{msg} - {self.doc.changed_bytes} byte(s) changed")

    def _update_title_dirty(self)->None:self.title(APP_TITLE+(" *" if self.doc.dirty else ""))

    def on_close(self)->None:
        if self.doc.dirty and not messagebox.askyesno("Unsaved edits","There are unexported changes. Close anyway?"):return
        self.destroy()


def main()->None:
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        # Used by the Windows release gate; never opens or modifies a user save.
        import hashlib
        import json
        import platform
        import traceback
        report_path = Path(sys.argv[2]).resolve()
        app = None
        try:
            app = EditorApp()
            app.withdraw()
            app.update()
            if app.weapon_db is None:
                raise RuntimeError("Bundled weapon database did not load")
            report = {
                "ok": True, "version": APP_VERSION, "title": app.title(),
                "frozen": bool(getattr(sys, "frozen", False)),
                "architecture": platform.machine(),
                "weapon_records": len(app.weapon_db.blob) // WEAPON_RECORD_SIZE,
                "weapon_database_sha256": hashlib.sha256(app.weapon_db.blob).hexdigest(),
            }
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except Exception:
            report_path.write_text(json.dumps({"ok": False, "error": traceback.format_exc()}), encoding="utf-8")
            raise SystemExit(1)
        finally:
            if app is not None:
                app.destroy()
        return
    app=EditorApp();app.mainloop()


if __name__=="__main__":main()
