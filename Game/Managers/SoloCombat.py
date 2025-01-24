import random
from datetime import datetime
from typing import Dict, List, Tuple
from Game.Models.Monster import Monster
from Game.Models.Player import Player
from Game.Database.database import Database

class CombatSystem:
    @staticmethod
    def calculate_power_score(entity: Player | Monster, is_player: bool = True) -> float:
        """Calculate power score for either player or monster"""
        base_score = 0
        
        if is_player:
            # Base stats contribution
            base_score += entity.stats["strength"] * 1.5
            base_score += entity.stats["agility"] * 1.2
            base_score += entity.stats["vitality"] * 1.0
            base_score += entity.level * 5
            
            # Equipment bonus (we can expand this later)
            equipment_bonus = 0
            for item in entity.equipment.values():
                if item:
                    equipment_bonus += item.get('power', 0)
            base_score += equipment_bonus
        else:
            # Monster power calculation
            base_score += entity.level * 6
            base_score += entity.damage * 1.3
            base_score += entity.defense
            
            # Rarity multipliers
            rarity_multipliers = {
                "E": 1.0,
                "D": 1.3,
                "C": 1.6,
                "B": 2.0,
                "A": 2.5,
                "S": 3.0
            }
            base_score *= rarity_multipliers.get(entity.rarity, 1.0)
        
        # Add randomness factor (mindset variable)
        mindset = random.uniform(0, 10)
        final_score = base_score * (1 + (mindset / 20))  # Mindset can affect up to ±50%
        
        return final_score

class RaidManager:
    def __init__(self):
        self.combat_system = CombatSystem()

    async def generate_monsters(self, tower_level: int, player_level: int) -> List[Monster]:
        db = Database()
        monsters_collection = db.get_monsters_collection()
        
        # Define monster ranges by rarity
        rarity_ranges = {
            "E": (1, 10),   # Easiest monsters
            "D": (11, 20),  # Next difficulty tier
            "C": (21, 30),
            "B": (31, 40),
            "A": (41, 50),
            "S": (51, 60)   # Hardest monsters
        }
        
        # Determine rarity based on tower level
        current_rarity = "E"
        for rarity, (min_level, max_level) in rarity_ranges.items():
            if tower_level <= max_level:
                current_rarity = rarity
                break
        
        # Query monsters for current rarity range
        monster_query = {
            "monster_id": {"$regex": f"^{current_rarity}"}
        }
        
        potential_monsters = list(monsters_collection.find(monster_query))
        
        # Randomly select monsters
        selected_monsters = []
        num_monsters = random.randint(3, min(len(potential_monsters), 7))
        selected_monster_data = random.sample(potential_monsters, num_monsters)
        
        for monster_data in selected_monster_data:
            monster = Monster(
                monster_id=monster_data["monster_id"],
                name=monster_data["name"],
                level=monster_data["level"],
                rarity=current_rarity,
                monster_type=monster_data.get("monster_type", "generic"),
                hp=monster_data.get("base_hp", 50),
                damage=monster_data.get("base_damage", 5),
                defense=monster_data.get("base_defense", 3),
                experience_reward=monster_data.get("experience_reward", 15),
                gold_reward=monster_data.get("gold_reward", 10),
                loot_table=monster_data.get("loot_table", [])
            )
            
            selected_monsters.append(monster)
        
        return selected_monsters
    
    async def process_raid(self, player: Player, tower_level: int) -> Dict:
        monsters = await self.generate_monsters(tower_level, player.level)
        
        raid_results = {
            "monsters_defeated": [],
            "monsters_defeated_by": [],
            "total_rewards": {"gold": 0, "experience": 0},
            "battles": [],
            "raid_complete": False,
            "player_survived": True,
            "damage_taken": 0
        }
        
        for monster in monsters:
            if player.current_hp <= 0:
                raid_results["player_survived"] = False
                break
                    
            battle_result = await self.process_battle(player, monster)
            raid_results["battles"].append(battle_result)
            
            if battle_result["player_won"]:
                raid_results["monsters_defeated"].append(monster.monster_id)
                raid_results["total_rewards"]["gold"] += battle_result["rewards"]["gold"]
                raid_results["total_rewards"]["experience"] += battle_result["rewards"]["experience"]
            else:
                raid_results["monsters_defeated_by"].append(monster.monster_id)
                player.current_hp -= battle_result["damage_taken"]
                raid_results["damage_taken"] += battle_result["damage_taken"]
                break
        
        raid_results["raid_complete"] = len(raid_results["monsters_defeated"]) == len(monsters)
        return raid_results


    async def process_battle(self, player: Player, monster: Monster) -> Dict:
        player_power = self.combat_system.calculate_power_score(player, True)
        monster_power = self.combat_system.calculate_power_score(monster, False)
            
        player_wins = player_power > monster_power
        
        rewards = {
            "gold": monster.gold_reward if player_wins else 0,
            "experience": monster.experience_reward if player_wins else 0
        }
        
        damage_taken = monster.damage if not player_wins else 0
        
        return {
            "player_won": player_wins,
            "damage_taken": damage_taken,
            "rewards": rewards,
            "monster_id": monster.monster_id
        }

def handle_player_death(player: Player) -> List[Dict]:
    """
    Handle player death consequences - drop items and return to camp
    Returns list of dropped items
    """
    dropped_items = []
    
    # Chance to drop equipped items (30% chance per item)
    for slot, item in player.equipment.items():
        if item and random.random() < 0.3:
            dropped_items.append({
                "slot": slot,
                "item": item
            })
            player.equipment[slot] = None
    
    # Drop 20% of gold
    gold_loss = int(player.gold * 0.2)
    player.gold -= gold_loss
    
    # Reset player state
    player.current_hp = player.max_hp * 0.1  # Return with 10% HP
    player.current_party_id = None  # Remove from party if in one
    
    return dropped_items

def create_raid_summary(results: Dict) -> str:
    summary = "🗡️ **Raid Summary** 🗡️"
    
    summary += f"\n❤️ **Health Lost:** {results['damage_taken']}\n"
    
    summary += "\n**Monsters Defeated:**\n"
    for monster_id in results["monsters_defeated"]:
        summary += f"✅ {monster_id}\n"
    
    if results["monsters_defeated_by"]:
        summary += "\n**Monsters that Defeated You:**\n"
        for monster_id in results["monsters_defeated_by"]:
            summary += f"❌ {monster_id}\n"
    
    summary += "\n**Rewards:**\n"
    summary += f"💰 Gold: {results['total_rewards']['gold']:.0f}\n"
    summary += f"✨ Experience: {results['total_rewards']['experience']:.0f}\n"
    
    if results["raid_complete"]:
        summary += "\n🏆 Raid Complete! 🏆"
    elif results["player_survived"]:
        summary += "\n⚠️ Raid Abandoned - Retreated safely"
    else:
        summary += "\n💀 Raid Failed - Player Defeated"
    
    return summary

# Example usage in a Discord command
async def handle_raid_command(player: Player, tower_level: int):
    db = Database()
    players_collection = db.get_players_collection()
    
    raid_manager = RaidManager()
    results = await raid_manager.process_raid(player, tower_level)
    
    # Update player based on results
    player.gold += results["total_rewards"]["gold"]
    player.experience += results["total_rewards"]["experience"]
    
    if not results["player_survived"]:
        dropped_items = handle_player_death(player)
        results["dropped_items"] = dropped_items
    
    # Update player in database
    players_collection.update_one(
        {"discord_id": player.discord_id}, 
        {"$set": {
            "current_hp": player.current_hp,
            "gold": player.gold,
            "experience": player.experience
        }}
    )
    
    # Generate raid summary
    summary = create_raid_summary(results)
    return summary