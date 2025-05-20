#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dota 2 KillSteal Script - Versão Aprimorada

Este script monitora o estado do jogo Dota 2 e tenta usar habilidades para
conseguir o último golpe (killsteal) em inimigos com pouca vida.

Características:
- Integração com o Dota 2 via console de desenvolvedor
- Detecção de estado do jogo (vida dos inimigos, mana, cooldowns)
- Sistema de configuração flexível
- Logging detalhado para depuração
- Tratamento de erros robusto
"""

import time
import json
import os
import logging
import threading
import keyboard
import pyautogui
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("killsteal.log", mode='a')
    ]
)
logger = logging.getLogger("KillSteal")


class ConfigManager:
    """Gerencia as configurações do script com suporte a arquivo de configuração."""
    
    DEFAULT_CONFIG = {
        "dota_window_title": "Dota 2",
        "check_interval": 0.5,  # Intervalo entre verificações em segundos
        "killsteal_cooldown": 3.0,  # Tempo mínimo entre tentativas de killsteal
        "enable_hotkey": "F8",  # Tecla para ativar/desativar o script
        "debug_mode": False,
        "use_console_commands": True,  # Se falso, usa simulação de teclas
        "console_command_prefix": "dota_execute",
        "hero_abilities": {
            # Formato: "nome_do_heroi": [{"name": "nome_da_habilidade", "key": "tecla", "damage": valor, "mana_cost": valor}, ...]
            "npc_dota_hero_lina": [
                {"name": "lina_dragon_slave", "key": "q", "damage": 280, "mana_cost": 100},
                {"name": "lina_light_strike_array", "key": "w", "damage": 250, "mana_cost": 110},
                {"name": "lina_laguna_blade", "key": "r", "damage": 850, "mana_cost": 280}
            ],
            "npc_dota_hero_lion": [
                {"name": "lion_impale", "key": "q", "damage": 260, "mana_cost": 110},
                {"name": "lion_finger_of_death", "key": "r", "damage": 800, "mana_cost": 250}
            ],
            # Adicione mais heróis conforme necessário
        }
    }
    
    def __init__(self, config_file: str = "killsteal_config.json"):
        """Inicializa o gerenciador de configurações."""
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Carrega configurações do arquivo ou usa padrões."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                    # Mesclar com configurações padrão para garantir que todos os campos existam
                    config = self.DEFAULT_CONFIG.copy()
                    self._deep_update(config, loaded_config)
                    logger.info(f"Configurações carregadas de {self.config_file}")
                    return config
        except Exception as e:
            logger.error(f"Erro ao carregar configurações: {e}")
        
        # Se falhar ou arquivo não existir, usar configurações padrão
        logger.info("Usando configurações padrão")
        return self.DEFAULT_CONFIG.copy()
    
    def _deep_update(self, d: Dict, u: Dict) -> None:
        """Atualiza recursivamente um dicionário com outro."""
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                self._deep_update(d[k], v)
            else:
                d[k] = v
    
    def save_config(self) -> bool:
        """Salva as configurações atuais no arquivo."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
            logger.info(f"Configurações salvas em {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar configurações: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Obtém um valor de configuração usando notação de ponto."""
        keys = key.split('.')
        value = self.config
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> None:
        """Define um valor de configuração usando notação de ponto."""
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            if k not in config or not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value


class Ability:
    """Representa uma habilidade de herói no Dota 2."""
    
    def __init__(self, name: str, key: str, damage: float, mana_cost: float, cooldown: float = 0.0):
        """
        Inicializa uma habilidade.
        
        Args:
            name: Nome interno da habilidade (ex: "lina_dragon_slave")
            key: Tecla associada à habilidade (ex: "q", "w", "e", "r", "d", "f")
            damage: Dano base da habilidade
            mana_cost: Custo de mana da habilidade
            cooldown: Tempo de recarga da habilidade em segundos
        """
        self.name = name
        self.key = key.lower()
        self.damage = damage
        self.mana_cost = mana_cost
        self.cooldown = cooldown
        self.last_cast_time = 0
    
    def is_ready(self) -> bool:
        """Verifica se a habilidade está pronta para uso (fora de cooldown)."""
        return time.time() - self.last_cast_time > self.cooldown
    
    def cast(self) -> None:
        """Registra o momento do uso da habilidade."""
        self.last_cast_time = time.time()
    
    def get_effective_damage(self, magic_resistance: float = 0.25) -> float:
        """
        Calcula o dano efetivo considerando a resistência mágica.
        
        Args:
            magic_resistance: Valor da resistência mágica (0.25 = 25%)
            
        Returns:
            Dano efetivo após redução pela resistência mágica
        """
        return self.damage * (1 - magic_resistance)


class Hero:
    """Representa um herói no Dota 2."""
    
    def __init__(self, name: str, config_manager: ConfigManager):
        """
        Inicializa um herói.
        
        Args:
            name: Nome interno do herói (ex: "npc_dota_hero_lina")
            config_manager: Gerenciador de configurações
        """
        self.name = name
        self.config = config_manager
        self.abilities = {}
        self.mana = 1000  # Valor padrão, deve ser atualizado com o valor real
        self.channeling = False
        self.invisible = False
        
        # Carregar habilidades do herói da configuração
        self._load_abilities()
    
    def _load_abilities(self) -> None:
        """Carrega as habilidades do herói a partir da configuração."""
        hero_abilities = self.config.get(f"hero_abilities.{self.name}", [])
        
        if not hero_abilities:
            # Tentar carregar da lista de nukes do script original
            from killsteal import nuke_ability_list
            ability_names = nuke_ability_list.get(self.name, [])
            
            if ability_names:
                # Criar habilidades com valores padrão
                for i, ability_name in enumerate(ability_names):
                    key = chr(ord('q') + i) if i < 6 else 'd'  # q, w, e, r, d, f
                    self.add_ability(Ability(
                        name=ability_name,
                        key=key,
                        damage=300,  # Valor padrão
                        mana_cost=100,  # Valor padrão
                        cooldown=10  # Valor padrão
                    ))
                logger.info(f"Carregadas {len(ability_names)} habilidades padrão para {self.name}")
            else:
                logger.warning(f"Nenhuma habilidade encontrada para o herói {self.name}")
        else:
            # Carregar da configuração
            for ability_data in hero_abilities:
                self.add_ability(Ability(
                    name=ability_data["name"],
                    key=ability_data["key"],
                    damage=ability_data["damage"],
                    mana_cost=ability_data["mana_cost"],
                    cooldown=ability_data.get("cooldown", 10)
                ))
            logger.info(f"Carregadas {len(hero_abilities)} habilidades da configuração para {self.name}")
    
    def add_ability(self, ability: Ability) -> None:
        """
        Adiciona uma habilidade ao herói.
        
        Args:
            ability: Objeto Ability a ser adicionado
        """
        self.abilities[ability.name] = ability
    
    def get_ability(self, ability_name: str) -> Optional[Ability]:
        """
        Obtém uma habilidade pelo nome.
        
        Args:
            ability_name: Nome da habilidade
            
        Returns:
            Objeto Ability ou None se não encontrado
        """
        return self.abilities.get(ability_name, None)
    
    def is_channeling(self) -> bool:
        """Verifica se o herói está canalizando uma habilidade."""
        # Na implementação real, isso seria detectado do jogo
        return self.channeling
    
    def is_invisible(self) -> bool:
        """Verifica se o herói está invisível."""
        # Na implementação real, isso seria detectado do jogo
        return self.invisible
    
    def cast(self, ability: Ability, target: 'Enemy', game_interface: 'GameInterface') -> bool:
        """
        Usa uma habilidade em um alvo.
        
        Args:
            ability: Habilidade a ser usada
            target: Alvo da habilidade
            game_interface: Interface com o jogo
            
        Returns:
            True se a habilidade foi usada com sucesso, False caso contrário
        """
        if not ability.is_ready() or self.mana < ability.mana_cost:
            return False
        
        success = game_interface.cast_ability(self, ability, target)
        
        if success:
            ability.cast()  # Registrar o uso
            self.mana -= ability.mana_cost  # Reduzir mana
            logger.info(f"{datetime.now()} - {self.name} usou {ability.name} em {target.name}")
        
        return success


class Enemy:
    """Representa um inimigo no Dota 2."""
    
    def __init__(self, name: str, health: float = 1000, magic_resistance: float = 0.25):
        """
        Inicializa um inimigo.
        
        Args:
            name: Nome do inimigo
            health: Vida atual do inimigo
            magic_resistance: Resistência mágica do inimigo (0.25 = 25%)
        """
        self.name = name
        self.health = health
        self.magic_resistance = magic_resistance
    
    def is_alive(self) -> bool:
        """Verifica se o inimigo está vivo."""
        return self.health > 0
    
    def is_enemy(self, hero: Hero) -> bool:
        """
        Verifica se é um inimigo do herói.
        
        Args:
            hero: Herói a ser verificado
            
        Returns:
            True se for inimigo, False caso contrário
        """
        # Na implementação real, isso seria determinado pelo jogo
        return True
    
    def update_health(self, health: float) -> None:
        """
        Atualiza a vida do inimigo.
        
        Args:
            health: Novo valor de vida
        """
        self.health = health


class GameInterface:
    """Interface para interação com o jogo Dota 2."""
    
    def __init__(self, config_manager: ConfigManager):
        """
        Inicializa a interface com o jogo.
        
        Args:
            config_manager: Gerenciador de configurações
        """
        self.config = config_manager
        self.use_console_commands = self.config.get("use_console_commands", True)
        self.console_command_prefix = self.config.get("console_command_prefix", "dota_execute")
        self.dota_window_title = self.config.get("dota_window_title", "Dota 2")
    
    def cast_ability(self, hero: Hero, ability: Ability, target: Enemy) -> bool:
        """
        Usa uma habilidade em um alvo.
        
        Args:
            hero: Herói que usará a habilidade
            ability: Habilidade a ser usada
            target: Alvo da habilidade
            
        Returns:
            True se a habilidade foi usada com sucesso, False caso contrário
        """
        try:
            if self.use_console_commands:
                # Usar comando de console
                command = f"{self.console_command_prefix} {hero.name} {ability.name} {target.name}"
                self._execute_console_command(command)
            else:
                # Simular pressionamento de tecla
                self._focus_dota_window()
                # Pressionar a tecla da habilidade
                pyautogui.press(ability.key)
                # Clicar no alvo (na implementação real, precisaria das coordenadas do alvo)
                # pyautogui.click(x, y)
                
                # Como não temos as coordenadas reais, vamos apenas simular um clique
                pyautogui.click()
            
            return True
        except Exception as e:
            logger.error(f"Erro ao usar habilidade: {e}")
            return False
    
    def _execute_console_command(self, command: str) -> None:
        """
        Executa um comando no console do Dota 2.
        
        Args:
            command: Comando a ser executado
        """
        try:
            # Na implementação real, isso enviaria o comando para o console do Dota 2
            # Aqui estamos apenas simulando
            logger.debug(f"Executando comando: {command}")
            
            # Abrir console (geralmente é a tecla `)
            self._focus_dota_window()
            pyautogui.press('`')
            time.sleep(0.1)
            
            # Digitar e executar comando
            pyautogui.write(command)
            pyautogui.press('enter')
            
            # Fechar console
            pyautogui.press('`')
        except Exception as e:
            logger.error(f"Erro ao executar comando no console: {e}")
    
    def _focus_dota_window(self) -> bool:
        """
        Foca na janela do Dota 2.
        
        Returns:
            True se conseguiu focar, False caso contrário
        """
        try:
            # Na implementação real, isso focaria na janela do Dota 2
            # Aqui estamos apenas simulando
            logger.debug(f"Focando na janela do Dota 2")
            
            # Implementação real usando pygetwindow (não incluído aqui para simplificar)
            # import pygetwindow as gw
            # dota_windows = gw.getWindowsWithTitle(self.dota_window_title)
            # if dota_windows:
            #     dota_windows[0].activate()
            #     return True
            
            return True
        except Exception as e:
            logger.error(f"Erro ao focar na janela do Dota 2: {e}")
            return False
    
    def get_game_state(self) -> Dict[str, Any]:
        """
        Obtém o estado atual do jogo.
        
        Returns:
            Dicionário com informações do estado do jogo
        """
        # Na implementação real, isso obteria informações do jogo
        # Aqui estamos apenas retornando valores simulados
        return {
            "hero_mana": 1000,
            "hero_channeling": False,
            "hero_invisible": False,
            "enemies": [
                {"name": "enemy1", "health": 500, "magic_resistance": 0.25},
                {"name": "enemy2", "health": 200, "magic_resistance": 0.3},
                {"name": "enemy3", "health": 100, "magic_resistance": 0.2}
            ]
        }


class KillStealManager:
    """Gerencia a funcionalidade de killsteal."""
    
    def __init__(self, config_file: str = "killsteal_config.json"):
        """
        Inicializa o gerenciador de killsteal.
        
        Args:
            config_file: Caminho para o arquivo de configuração
        """
        self.config_manager = ConfigManager(config_file)
        self.game_interface = GameInterface(self.config_manager)
        
        # Herói atual (na implementação real, seria detectado do jogo)
        self.hero = Hero("npc_dota_hero_lina", self.config_manager)
        
        # Lista de inimigos (na implementação real, seria atualizada do jogo)
        self.enemies = []
        
        # Controle de tempo
        self.last_check_time = 0
        self.killsteal_cooldown = self.config_manager.get("killsteal_cooldown", 3.0)
        self.check_interval = self.config_manager.get("check_interval", 0.5)
        
        # Estado do script
        self.running = False
        self.enabled = False
        self.thread = None
        
        # Configurar hotkey para ativar/desativar
        self.enable_hotkey = self.config_manager.get("enable_hotkey", "F8")
        keyboard.add_hotkey(self.enable_hotkey, self.toggle_enabled)
    
    def toggle_enabled(self) -> None:
        """Alterna entre ativado e desativado."""
        self.enabled = not self.enabled
        logger.info(f"KillSteal {'ativado' if self.enabled else 'desativado'}")
    
    def update_game_state(self) -> None:
        """Atualiza o estado do jogo."""
        try:
            # Na implementação real, isso obteria informações do jogo
            game_state = self.game_interface.get_game_state()
            
            # Atualizar mana do herói
            self.hero.mana = game_state.get("hero_mana", 1000)
            self.hero.channeling = game_state.get("hero_channeling", False)
            self.hero.invisible = game_state.get("hero_invisible", False)
            
            # Atualizar inimigos
            self.enemies = []
            for enemy_data in game_state.get("enemies", []):
                enemy = Enemy(
                    name=enemy_data["name"],
                    health=enemy_data["health"],
                    magic_resistance=enemy_data["magic_resistance"]
                )
                self.enemies.append(enemy)
        except Exception as e:
            logger.error(f"Erro ao atualizar estado do jogo: {e}")
    
    def can_cast_skill(self, hero: Hero, skill: Ability) -> bool:
        """
        Verifica se uma habilidade pode ser usada.
        
        Args:
            hero: Herói que usará a habilidade
            skill: Habilidade a ser verificada
            
        Returns:
            True se a habilidade pode ser usada, False caso contrário
        """
        return hero.mana >= skill.mana_cost and skill.is_ready()
    
    def should_cast_skill(self, hero: Hero, enemy: Enemy, skill: Ability) -> bool:
        """
        Verifica se uma habilidade deve ser usada para killsteal.
        
        Args:
            hero: Herói que usará a habilidade
            enemy: Inimigo alvo
            skill: Habilidade a ser verificada
            
        Returns:
            True se a habilidade deve ser usada, False caso contrário
        """
        effective_damage = skill.get_effective_damage(enemy.magic_resistance)
        return enemy.health < effective_damage
    
    def killsteal(self) -> None:
        """Tenta usar habilidades para conseguir killsteal."""
        current_time = time.time()
        
        # Verificar cooldown
        if current_time - self.last_check_time < self.killsteal_cooldown:
            return
        
        # Verificar se o herói pode usar habilidades
        if self.hero.is_channeling() or self.hero.is_invisible():
            return
        
        # Verificar inimigos
        for enemy in self.enemies:
            if enemy.is_alive() and enemy.is_enemy(self.hero):
                # Verificar habilidades
                for ability_name, ability in self.hero.abilities.items():
                    if (self.can_cast_skill(self.hero, ability) and 
                        self.should_cast_skill(self.hero, enemy, ability)):
                        # Usar habilidade
                        if self.hero.cast(ability, enemy, self.game_interface):
                            self.last_check_time = current_time
                            return
    
    def _main_loop(self) -> None:
        """Loop principal do script."""
        while self.running:
            try:
                if self.enabled:
                    # Atualizar estado do jogo
                    self.update_game_state()
                    
                    # Tentar killsteal
                    self.killsteal()
                
                # Aguardar próximo ciclo
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Erro no loop principal: {e}")
                time.sleep(1)  # Esperar um pouco antes de tentar novamente
    
    def start(self) -> None:
        """Inicia o script."""
        if self.running:
            logger.warning("Script já está em execução")
            return
        
        logger.info("Iniciando KillSteal Script")
        logger.info(f"Pressione {self.enable_hotkey} para ativar/desativar")
        
        # Iniciar thread principal
        self.running = True
        self.thread = threading.Thread(target=self._main_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self) -> None:
        """Para o script."""
        logger.info("Parando KillSteal Script")
        self.running = False
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        
        # Salvar configurações
        self.config_manager.save_config()


def main():
    """Função principal."""
    # Configurar argumentos de linha de comando
    import argparse
    parser = argparse.ArgumentParser(description="Dota 2 KillSteal Script")
    parser.add_argument("--config", type=str, default="killsteal_config.json",
                        help="Caminho para o arquivo de configuração")
    parser.add_argument("--debug", action="store_true",
                        help="Ativar modo de depuração")
    args = parser.parse_args()
    
    # Criar e iniciar o gerenciador de killsteal
    killsteal_manager = KillStealManager(config_file=args.config)
    
    # Ativar modo de depuração se solicitado
    if args.debug:
        killsteal_manager.config_manager.set("debug_mode", True)
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Modo de depuração ativado")
    
    try:
        killsteal_manager.start()
        
        # Manter o programa em execução
        print("KillSteal Script em execução. Pressione Ctrl+C para sair.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Script interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro ao executar o script: {e}")
    finally:
        killsteal_manager.stop()


if __name__ == "__main__":
    main()
