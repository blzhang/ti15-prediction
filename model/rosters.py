"""TI15 16 队首发名单 — 来源 01-ti15-facts.md §2.3（Liquipedia 仲裁 + OpenDota account_id）"""

ROSTERS = {
    # ---- 直邀 7 ----
    "Aurora Gaming":   {"Nightfall": 124801257, "Mikoto": 301750126, "Ws": 126842529,
                        "Mira": 256156323, "kaori": 320219866},
    "BoomBoys":        {"Kiritych~": 172099728, "gpk~": 480412663, "MieRo": 165564598,
                        "Save-": 317880638, "Kataomi": 196878136},
    "Iron Wing":       {"Pure": 331855530, "bzm": 93618577, "33": 86698277,
                        "Ari": 346412363, "Whitemon": 136829091},
    "Team Falcons":    {"skiter": 100058342, "Malr1ne": 898455820, "ATF": 183719386,
                        "Cr1t-": 25907144, "Sneyking": 10366616},
    "Team Liquid":     {"m1CKe": 152962063, "Nisha": 201358612, "Ace": 97590558,
                        "Boxi": 77490514, "tOfu": 16497807},
    "Team Yandex":     {"watson": 171262902, "CHIRA_JUNIOR": 312436974, "DM": 56351509,
                        "Saksa": 103735745, "Malady": 93817671},
    "Xtreme Gaming":   {"Ame": 898754153, "NothingToSay": 173978074, "Xxs": 129958758,
                        "fy": 101695162, "xNova": 94296097},
    # ---- 预选 9 ----
    "Team Spirit":     {"Yatoro": 321580662, "Larl": 106305042, "Collapse": 302214028,
                        "not me": 218231587, "rue": 847565596},
    "TEAM VISION":     {"Satanic": 1044002267, "No[o]ne-": 106573901, "Noticed": 195108598,
                        "9Class": 164199202, "Dukalis": 73401082},
    "Nigma Galaxy":    {"SumaiL": 111620041, "lorenof": 210053851, "Davai": 138880576,
                        "OmaR": 152168157, "GH": 101356886},
    "HULIGANI":        {"ssnovv1": 320017600, "Mirage`": 140251702, "Corrupted": 92487440,
                        "sayuw": 145065875, "RESPECT": 123787715},
    "Team Resilience": {"YSR-04E": 170896543, "Echozz": 315272623, "niu": 145957968,
                        "planet": 150961567, "zzq": 249835593},
    "Vici Gaming":     {"shiro": 320252024, "Xm": 137129583, "Bach": 118134220,
                        "XinQ": 157475523, "y`": 111114687},
    "OG":              {"Natsumi": 355168766, "Yopaj-": 324277900, "Raven": 132309493,
                        "TIMS": 155494381, "skem": 100594231},
    "GamerLegion":     {"Ghost": 206642367, "RCY": 154974246, "Fayde": 160119017,
                        "Bignum": 90423751, "Speeed": 191362875},
    "LGD Gaming":      {"Yuma": 177203952, "TaiLung": 1026694469, "Wisper": 292921272,
                        "Thiolicor": 105045291, "KJ": 81306398},
}

# 位置：1=carry 2=mid 3=off 4=soft sup 5=hard sup（顺序与上面 dict 一致）
POSITIONS = {t: {p: i + 1 for i, p in enumerate(r)} for t, r in ROSTERS.items()}

# 赛区（01-ti15-facts.md §2.2）
REGION = {
    "Aurora Gaming": "EU", "BoomBoys": "EU", "Iron Wing": "EU", "Team Falcons": "EU",
    "Team Liquid": "EU", "Team Yandex": "EU", "Team Spirit": "EU", "TEAM VISION": "EU",
    "Nigma Galaxy": "EU", "HULIGANI": "EU",
    "Xtreme Gaming": "CN", "Team Resilience": "CN", "Vici Gaming": "CN",
    "OG": "SEA", "GamerLegion": "NA", "LGD Gaming": "SA",
}

# 阵容变动等级（01-ti15-facts.md §2.4）：A=没动 B=换1 C=换2/重大角色变动 D=换3+/全新
ROSTER_CHURN = {
    "Team Falcons": "A",
    "BoomBoys": "B", "TEAM VISION": "B", "Team Resilience": "B", "GamerLegion": "B",
    "Iron Wing": "B", "LGD Gaming": "B", "HULIGANI": "B", "Nigma Galaxy": "B",
    "Team Liquid": "C", "Xtreme Gaming": "C", "Team Spirit": "C", "Team Yandex": "C",
    "Aurora Gaming": "D", "Vici Gaming": "D", "OG": "D",
}

ACCOUNT_TO_TEAM = {aid: t for t, r in ROSTERS.items() for aid in r.values()}
ACCOUNT_TO_NAME = {aid: p for r in ROSTERS.values() for p, aid in r.items()}

assert len(ACCOUNT_TO_TEAM) == 80, f"account_id 去重后应为 80，实为 {len(ACCOUNT_TO_TEAM)}"
assert set(REGION) == set(ROSTERS) and set(ROSTER_CHURN) == set(ROSTERS)
