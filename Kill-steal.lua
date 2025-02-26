local last_check_time = 0

Hero = {}
Hero.__index = Hero

function Hero:new(name, mana)
    local obj = {name = name, mana = mana, abilities = {}}
    setmetatable(obj, Hero)
    return obj
end

function Hero:add_ability(ability)
    self.abilities[ability.name] = ability
end

function Hero:get_ability(ability_name)
    return self.abilities[ability_name]
end

function Hero:is_channeling()
    return false
end

function Hero:is_invisible()
    return false
end

function Hero:cast(ability, target)
    local command = string.format("dota_execute %s %s %s", self.name, ability.name, target.name)
    os.execute(command)
    print(os.date("%Y-%m-%d %H:%M:%S") .. " - " .. self.name .. " usou " .. ability.name .. " em " .. target.name)
end

Ability = {}
Ability.__index = Ability

function Ability:new(name, mana_cost, damage)
    local obj = {name = name, mana_cost = mana_cost, damage = damage}
    setmetatable(obj, Ability)
    return obj
end

function Ability:is_ready()
    return true
end

Enemy = {}
Enemy.__index = Enemy

function Enemy:new(name, health, magic_resistance)
    local obj = {name = name, health = health, magic_resistance = magic_resistance}
    setmetatable(obj, Enemy)
    return obj
end

function Enemy:is_alive()
    return self.health > 0
end

function Enemy:is_enemy(hero)
    return true
end

nuke_ability_list = {
    npc_dota_hero_abaddon = {"abaddon_death_coil"},
    npc_dota_hero_abyssal_underlord = {"abyssal_underlord_firestorm"},
    npc_dota_hero_bane = {"bane_brain_sap"},
    npc_dota_hero_beastmaster = {"beastmaster_wild_axes"},
    npc_dota_hero_bloodseeker = {"bloodseeker_blood_bath"},
    npc_dota_hero_bounty_hunter = {"bounty_hunter_shuriken_toss"},
    npc_dota_hero_brewmaster = {"brewmaster_thunder_clap"},
    npc_dota_hero_bristleback = {"bristleback_quill_spray"},
    npc_dota_hero_broodmother = {"broodmother_spawn_spiderlings"},
    npc_dota_hero_centaur = {"centaur_double_edge"},
    npc_dota_hero_chen = {"chen_test_of_faith"},
    npc_dota_hero_crystal_maiden = {"crystal_maiden_crystal_nova"},
    npc_dota_hero_dazzle = {"dazzle_poison_touch"},
    npc_dota_hero_death_prophet = {"death_prophet_carrion_swarm"},
    npc_dota_hero_disruptor = {"disruptor_thunder_strike"},
    npc_dota_hero_dragon_knight = {"dragon_knight_breathe_fire"},
    npc_dota_hero_elder_titan = {"elder_titan_ancestral_spirit"},
    npc_dota_hero_gyrocopter = {"gyrocopter_rocket_barrage"},
    npc_dota_hero_kunkka = {"kunkka_torrent"},
    npc_dota_hero_legion_commander = {"legion_commander_overwhelming_odds"},
    npc_dota_hero_leshrac = {"leshrac_lightning_storm"},
    npc_dota_hero_lich = {"lich_frost_nova"},
    npc_dota_hero_lina = {"lina_dragon_slave"},
    npc_dota_hero_luna = {"luna_lucent_beam"},
    npc_dota_hero_magnataur = {"magnataur_shockwave"},
    npc_dota_hero_medusa = {"medusa_mystic_snake"},
    npc_dota_hero_mirana = {"mirana_starfall"},
    npc_dota_hero_morphling = {"morphling_adaptive_strike_agi"},
    npc_dota_hero_naga_siren = {"naga_siren_rip_tide"},
    npc_dota_hero_necrolyte = {"necrolyte_death_pulse"},
    npc_dota_hero_nevermore = {"nevermore_shadowraze1", "nevermore_shadowraze2", "nevermore_shadowraze3"},
    npc_dota_hero_night_stalker = {"night_stalker_void"},
    npc_dota_hero_nyx_assassin = {"nyx_assassin_mana_burn"},
    npc_dota_hero_ogre_magi = {"ogre_magi_fireblast"},
    npc_dota_hero_oracle = {"oracle_purifying_flames"},
    npc_dota_hero_phantom_assassin = {"phantom_assassin_stifling_dagger"},
    npc_dota_hero_phantom_lancer = {"phantom_lancer_spirit_lance"},
    npc_dota_hero_puck = {"puck_waning_rift"},
    npc_dota_hero_pugna = {"pugna_nether_blast"},
}

function can_cast_skill(hero, skill)
    return hero.mana >= skill.mana_cost and skill:is_ready()
end

function should_cast_skill(hero, enemy, skill)
    return enemy.health < skill.damage * (1 - enemy.magic_resistance)
end

function killsteal(hero, enemies)
    if os.time() - last_check_time < 3 then
        return
    end
    
    if hero:is_channeling() or hero:is_invisible() then
        return
    end
    
    for _, enemy in ipairs(enemies) do
        if enemy:is_alive() and enemy:is_enemy(hero) then
            local abilities = nuke_ability_list[hero.name] or {}
            for _, ability_name in ipairs(abilities) do
                local skill = hero:get_ability(ability_name)
                if skill and can_cast_skill(hero, skill) and should_cast_skill(hero, enemy, skill) then
                    hero:cast(skill, enemy)
                    last_check_time = os.time()
                    return
                end
            end
        end
    end
end
