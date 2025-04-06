import cv2
import numpy as np
import tkinter as tk
from datetime import datetime, timedelta
import pygetwindow as gw
import mss # Usar mss para captura de tela mais rápida
import mss.tools
import os
from typing import Optional, List, Dict, Any, Tuple

# --- Constantes de Configuração ---
TESSERACT_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe' # Mantido caso queira usar OCR no futuro
WEIGHTS_PATH = r"C:\Users\wesle\Desktop\Bot\yolov3.weights"
CFG_PATH = r"C:\Users\wesle\Desktop\Bot\yolov3.cfg"
NAMES_PATH = r"C:\Users\wesle\Desktop\Bot\classes.names"
DOTA_WINDOW_TITLE = "Dota 2"
CONFIDENCE_THRESHOLD = 0.5  # Limiar de confiança para detecção YOLO
DETECTION_INTERVAL_MS = 1500  # Intervalo entre detecções (em milissegundos)
OVERLAY_UPDATE_INTERVAL_MS = 500 # Intervalo de atualização do overlay
DUPLICATE_THRESHOLD_SECONDS = 2.0 # Tempo para considerar detecções como duplicadas

# Itens a serem detectados e suas durações (em segundos)
ITEM_DURATIONS = {
    "Observer Ward": 360,  # 6 minutos
    "Sentry Ward": 420,    # 7 minutos
    "Smoke of Deceit": 0   # Duração zero ou irrelevante para rastreamento de tempo
}
# ---------------------------------

# Verificar se os arquivos YOLO existem
for path in [WEIGHTS_PATH, CFG_PATH, NAMES_PATH]:
    if not os.path.exists(path):
        print(f"Erro Crítico: Arquivo não encontrado -> {path}")
        exit(1)

# Carregar os nomes das classes
try:
    with open(NAMES_PATH, "r") as f:
        CLASSES = [line.strip() for line in f.readlines()]
except Exception as e:
    print(f"Erro ao ler o arquivo de classes '{NAMES_PATH}': {e}")
    exit(1)

# Carregar o modelo YOLO
try:
    net = cv2.dnn.readNet(WEIGHTS_PATH, CFG_PATH)
    # Configurar backend e target (opcional, pode melhorar performance em algumas GPUs)
    # net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
    # net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
except cv2.error as e:
    print(f"Erro ao carregar o modelo YOLO: {e}")
    print("Verifique se os arquivos .weights e .cfg estão corretos e compatíveis.")
    exit(1)

# Obter nomes das camadas de saída
layer_names = net.getLayerNames()
try:
    # Ajuste para compatibilidade com diferentes versões do OpenCV
    unconnected_layers_indices = net.getUnconnectedOutLayers()
    if isinstance(unconnected_layers_indices[0], list) or isinstance(unconnected_layers_indices[0], np.ndarray):
         out_layers = [layer_names[i[0] - 1] for i in unconnected_layers_indices]
    else:
         out_layers = [layer_names[i - 1] for i in unconnected_layers_indices]
except IndexError as e:
    print(f"Erro ao obter camadas de saída: {e}. Verifique a compatibilidade do modelo/OpenCV.")
    exit(1)


# Lista para armazenar informações dos itens rastreados
# Cada item será um dicionário: {'id': unique_id, 'name': str, 'expiry': datetime, 'region': str, 'added_time': datetime}
tracked_items: List[Dict[str, Any]] = []

# --- Funções Auxiliares ---

def obter_regiao_do_mapa(x: int, y: int, largura_tela: int, altura_tela: int) -> str:
    """
    Determina uma região aproximada do mapa com base nas coordenadas da tela.
    NOTA: Esta é uma aproximação MUITO SIMPLES e não leva em conta a posição da câmera no jogo.
    A precisão será baixa. Para alta precisão, seria necessário detectar o minimapa.
    """
    if largura_tela == 0 or altura_tela == 0:
        return "Região Desconhecida"

    nx, ny = x / largura_tela, y / altura_tela

    # Ajuste as coordenadas e nomes das regiões conforme necessário
    if ny < 0.33:
        if nx < 0.33: return "Top Lane (Radiant)"
        elif nx < 0.66: return "Top Jungle (Radiant/Mid)"
        else: return "Top Lane/Jungle (Dire)"
    elif ny < 0.66:
        if nx < 0.15: return "Jungle (Radiant)"
        elif nx < 0.33: return "Mid Lane (Radiant Side)"
        elif nx < 0.66: return "Mid Lane (Centro)"
        elif nx < 0.85: return "Mid Lane (Dire Side)"
        else: return "Jungle (Dire)"
    else:
        if nx < 0.33: return "Bot Lane/Jungle (Radiant)"
        elif nx < 0.66: return "Bot Jungle (Dire/Mid)"
        else: return "Bot Lane (Dire)"

    return "Região Indefinida" # Fallback

def captura_tela(window_title: str) -> Optional[Tuple[np.ndarray, int, int, int, int]]:
    """Captura a tela da janela especificada usando mss."""
    try:
        dota_windows = gw.getWindowsWithTitle(window_title)
        if not dota_windows:
            # print(f"Janela '{window_title}' não encontrada.") # Comentado para não poluir console
            return None
        dota_window = dota_windows[0]

        # Corrigir possíveis problemas com janelas minimizadas ou com tamanho zero
        if not dota_window.isVisible or dota_window.isMinimized or dota_window.width <= 0 or dota_window.height <= 0:
             # print(f"Janela '{window_title}' não está visível ou tem tamanho inválido.")
             return None

        # Definir a região de captura com base na janela encontrada
        monitor = {
            "top": dota_window.top,
            "left": dota_window.left,
            "width": dota_window.width,
            "height": dota_window.height,
        }

        with mss.mss() as sct:
            sct_img = sct.grab(monitor)
            # Converter para formato OpenCV (BGR)
            img = np.array(sct_img)
            img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR) # Ou COLOR_RGB2BGR se BGRA não funcionar
            return img_bgr, dota_window.left, dota_window.top, dota_window.width, dota_window.height

    except Exception as e:
        print(f"Erro durante a captura de tela: {e}")
        return None

# --- Funções Principais ---

def detectar_itens():
    """Detecta itens na tela, calcula a região e adiciona à lista de rastreamento."""
    global tracked_items
    frame_data = captura_tela(DOTA_WINDOW_TITLE)

    if frame_data is None:
        return # Não fazer nada se a janela não for encontrada ou houver erro

    frame, win_x, win_y, win_w, win_h = frame_data
    height, width, _ = frame.shape

    # Criar blob para a rede neural
    blob = cv2.dnn.blobFromImage(frame, 1/255.0, (416, 416), swapRB=True, crop=False)
    net.setInput(blob)

    try:
        # Executar a detecção
        outputs = net.forward(out_layers)
    except cv2.error as e:
        print(f"Erro durante o forward pass da rede: {e}")
        return # Abortar detecção neste frame

    detections = []
    current_time = datetime.now()

    # Processar as saídas da rede
    for output in outputs:
        for detection in output:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]

            if confidence > CONFIDENCE_THRESHOLD and class_id < len(CLASSES):
                item_name = CLASSES[class_id]

                if item_name in ITEM_DURATIONS:
                    # Obter coordenadas do centro do item detectado na tela
                    center_x = int(detection[0] * width)
                    center_y = int(detection[1] * height)
                    # w_box = int(detection[2] * width) # Largura da caixa (não usada aqui)
                    # h_box = int(detection[3] * height) # Altura da caixa (não usada aqui)

                    regiao = obter_regiao_do_mapa(center_x, center_y, width, height)

                    # --- Verificação de Duplicatas ---
                    is_duplicate = False
                    for existing_item in tracked_items:
                        time_diff = (current_time - existing_item['added_time']).total_seconds()
                        if (existing_item['name'] == item_name and
                            existing_item['region'] == regiao and # Verifica mesma região (pode ser flexibilizado)
                            abs(time_diff) < DUPLICATE_THRESHOLD_SECONDS):
                            is_duplicate = True
                            break # Encontrou um item muito similar recentemente

                    if not is_duplicate:
                        detections.append({'name': item_name, 'region': regiao, 'time': current_time})

                        # Desenhar um círculo onde o item foi detectado (apenas para debug visual)
                        # cv2.circle(frame, (center_x, center_y), 10, (0, 255, 0), 2)


    # Adicionar novas detecções (não duplicadas) à lista de rastreamento
    for detected in detections:
        item_name = detected['name']
        regiao = detected['region']
        detection_time = detected['time']
        duration = ITEM_DURATIONS[item_name]

        # Só adicionar itens que têm duração (wards)
        if duration > 0:
            expiry_time = detection_time + timedelta(seconds=duration)
            unique_id = f"{item_name}_{regiao}_{detection_time.timestamp()}" # ID simples

            new_item_data = {
                'id': unique_id,
                'name': item_name,
                'expiry': expiry_time,
                'region': regiao,
                'added_time': detection_time # Hora que foi detectado pela primeira vez
            }
            tracked_items.append(new_item_data)
            print(f"[{detection_time.strftime('%H:%M:%S')}] {item_name} detectado em '{regiao}'. Expira às {expiry_time.strftime('%H:%M:%S')}.")
        else:
             # Para itens sem duração como Smoke, apenas registrar o evento se desejar
             print(f"[{detection_time.strftime('%H:%M:%S')}] {item_name} detectado em '{regiao}'.")

    # Exibir frame com detecções (opcional, para debug)
    # cv2.imshow("Dota 2 Detection", frame)
    # if cv2.waitKey(1) & 0xFF == ord('q'):
    #    pass # Não fechar aqui, o loop principal controla

# --- Configuração da Interface Gráfica (Overlay) ---
root = tk.Tk()
root.title("Dota 2 Item Tracker Overlay")
# Posição e tamanho inicial (ajuste conforme necessário)
initial_width = 450
initial_height = 300
root.geometry(f"{initial_width}x{initial_height}+100+100")

# Configurações da janela do overlay
root.attributes("-topmost", True)    # Sempre no topo
root.attributes("-alpha", 0.75)       # Nível de transparência (0.0 a 1.0)
root.overrideredirect(True)         # Remove a barra de título e bordas
root.configure(bg="black")          # Cor de fundo inicial

# --- Frame principal para conteúdo e scrollbar ---
main_frame = tk.Frame(root, bg="black")
main_frame.pack(fill=tk.BOTH, expand=True)

# --- Widget de Texto para exibir os alertas ---
# Usar uma fonte monoespaçada pode alinhar melhor os tempos
info_text = tk.Text(
    main_frame,
    font=("Consolas", 12), # Experimente fontes como Consolas, Courier New
    fg="white",
    bg="black",
    wrap=tk.WORD,        # Quebra de linha automática
    borderwidth=0,       # Sem borda interna
    highlightthickness=0 # Sem borda de foco
)
info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

# --- Scrollbar ---
scrollbar = tk.Scrollbar(main_frame, command=info_text.yview, bg='grey', troughcolor='black', width=10)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
info_text.config(yscrollcommand=scrollbar.set)

# --- Funcionalidade de Arrastar Janela ---
_offset_x = 0
_offset_y = 0

def start_move(event):
    global _offset_x, _offset_y
    _offset_x = event.x
    _offset_y = event.y

def do_move(event):
    global _offset_x, _offset_y
    x = root.winfo_pointerx() - _offset_x
    y = root.winfo_pointery() - _offset_y
    root.geometry(f"+{x}+{y}")

# Associar eventos do mouse ao frame principal para arrastar
main_frame.bind("<Button-1>", start_move)
main_frame.bind("<B1-Motion>", do_move)
# Também associar ao texto, caso o clique comece nele
info_text.bind("<Button-1>", start_move)
info_text.bind("<B1-Motion>", do_move)


# --- Função para Atualizar o Texto no Overlay ---
def atualizar_overlay():
    """Atualiza o widget de texto com os itens ativos e seus tempos restantes."""
    global tracked_items
    current_time = datetime.now()
    active_messages = []

    # Filtrar itens expirados e criar mensagens para os ativos
    valid_items = []
    for item in tracked_items:
        remaining_seconds = (item['expiry'] - current_time).total_seconds()
        if remaining_seconds > 0:
            valid_items.append(item) # Manter item na lista
            minutes, seconds = divmod(int(remaining_seconds), 60)
            # Formato: NomeItem [Região]: MM:SS
            message = f"{item['name']} [{item['region']}]: {minutes}:{seconds:02d}"
            active_messages.append(message)
        # else: item expirado, será removido implicitamente

    tracked_items = valid_items # Atualizar a lista global removendo os expirados

    # Limpar o conteúdo atual e inserir as novas mensagens
    info_text.configure(state=tk.NORMAL) # Habilitar edição
    info_text.delete(1.0, tk.END)
    if active_messages:
        info_text.insert(tk.END, "\n".join(active_messages))
    else:
        info_text.insert(tk.END, "Nenhum item rastreado.")
    info_text.configure(state=tk.DISABLED) # Desabilitar edição pelo usuário

    # Tornar o fundo preto transparente
    # ATENÇÃO: Isso pode não funcionar perfeitamente em todos os sistemas/compositors
    # Pode ser necessário ajustar a cor ou a abordagem dependendo do seu ambiente.
    try:
        root.attributes("-transparentcolor", "black")
    except tk.TclError:
         print("Aviso: -transparentcolor pode não ser suportado neste sistema.")
         root.configure(bg="#010101") # Usar um preto quase puro se transparente falhar


    # Agendar a próxima atualização
    root.after(OVERLAY_UPDATE_INTERVAL_MS, atualizar_overlay)


# --- Loop Principal ---
def loop_principal():
    """Executa a detecção de itens em intervalos regulares."""
    detectar_itens()
    # Agendar a próxima execução da detecção
    root.after(DETECTION_INTERVAL_MS, loop_principal)


# --- Iniciar Aplicação ---
print("Iniciando o rastreador de itens do Dota 2...")
print(f"Procurando pela janela: '{DOTA_WINDOW_TITLE}'")
print(f"Intervalo de detecção: {DETECTION_INTERVAL_MS / 1000.0} segundos")
print(f"Limiar de confiança: {CONFIDENCE_THRESHOLD}")

# Iniciar os loops de atualização e detecção
atualizar_overlay() # Inicia a atualização do overlay
loop_principal()    # Inicia a detecção de itens

# Iniciar o loop principal da interface gráfica Tkinter
root.mainloop()

print("Aplicação encerrada.")
# Opcional: Liberar recursos do OpenCV se necessário (geralmente não é preciso no fim do script)
# cv2.destroyAllWindows()
