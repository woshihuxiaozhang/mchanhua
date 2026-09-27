"""内置的 Minecraft 常用术语译法。

模型偶尔会把 Redstone 翻成"红石粉"、把 Netherite 翻成"下界岩"之类，
固定术语能显著提升一致性。用户配置里的 [glossary] 会覆盖这里的同名条目。
"""

DEFAULT_GLOSSARY: dict[str, str] = {
    "Redstone": "红石",
    "Redstone Dust": "红石粉",
    "Netherite": "下界合金",
    "Nether": "下界",
    "End": "末地",
    "Overworld": "主世界",
    "Ender": "末影",
    "Enchantment": "附魔",
    "Enchanting Table": "附魔台",
    "Anvil": "铁砧",
    "Durability": "耐久",
    "Stack": "堆叠",
    "Potion": "药水",
    "Splash Potion": "喷溅药水",
    "Lingering Potion": "滞留药水",
    "Beacon": "信标",
    "Crafting": "合成",
    "Inventory": "物品栏",
    "Hotbar": "快捷栏",
    "Right-click": "右键",
    "Left-click": "左键",
    "Shift-click": "Shift 点击",
    "Sneak": "潜行",
    "Spawn": "生成",
    "Biome": "生物群系",
    "Mob": "生物",
    "NPC": "NPC",
    "Quest": "任务",
    "Objective": "目标",
}

