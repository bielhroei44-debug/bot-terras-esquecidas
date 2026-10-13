import sqlite3
import logging
import random
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# Configuração de Logs
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Estados da Conversa
NOME, RACA, CONTINENTE, CLASSE, ATRIBUTOS, AVATAR = range(6)

# URL da imagem padrão do personagem
AVATAR_PADRAO = "https://images.unsplash.com/photo-1578632767115-351597cf2477?w=800&auto=format&fit=crop"

def escapar_markdown(texto):
    if not texto:
        return ""
    chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for c in chars:
        texto = str(texto).replace(c, f"\\{c}")
    return texto

# --- BANCO DE DADOS PERSISTENTE (SQLITE) ---

def init_db():
    conn = sqlite3.connect("terras_esquecidas.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jogadores (
            user_id INTEGER PRIMARY KEY,
            nome TEXT,
            raca TEXT,
            continente TEXT,
            classe TEXT,
            nivel INTEGER DEFAULT 1,
            xp_atual INTEGER DEFAULT 0,
            xp_max INTEGER DEFAULT 100,
            hp_atual INTEGER,
            hp_max INTEGER,
            mp_atual INTEGER,
            mp_max INTEGER,
            ouro INTEGER DEFAULT 100,
            avatar TEXT,
            forca INTEGER,
            defesa INTEGER,
            vitalidade INTEGER,
            agilidade INTEGER,
            inteligencia INTEGER,
            sorte INTEGER,
            carisma INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats_comunidade (
            chat_id INTEGER PRIMARY KEY,
            titulo TEXT,
            tipo TEXT,
            masmorra_thread_id INTEGER,
            data_registro DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def registrar_chat_db(chat_id, titulo, tipo):
    conn = sqlite3.connect("terras_esquecidas.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO chats_comunidade (chat_id, titulo, tipo)
        VALUES (?, ?, ?)
    """, (chat_id, titulo, tipo))
    conn.commit()
    conn.close()

def listar_chats_db():
    conn = sqlite3.connect("terras_esquecidas.db")
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, titulo, tipo, masmorra_thread_id FROM chats_comunidade")
    rows = cursor.fetchall()
    conn.close()
    return rows

def salvar_jogador_db(user_id, dados):
    conn = sqlite3.connect("terras_esquecidas.db")
    cursor = conn.cursor()
    atribs = dados.get("atributos_finais", {})
    cursor.execute("""
        INSERT OR REPLACE INTO jogadores (
            user_id, nome, raca, continente, classe, nivel, xp_atual, xp_max,
            hp_atual, hp_max, mp_atual, mp_max, ouro, avatar,
            forca, defesa, vitalidade, agilidade, inteligencia, sorte, carisma
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        dados.get("nome"),
        dados.get("raca"),
        dados.get("continente"),
        dados.get("classe"),
        dados.get("nivel", 1),
        dados.get("xp_atual", 0),
        dados.get("xp_max", 100),
        dados.get("hp_atual"),
        dados.get("hp_max"),
        dados.get("mp_atual"),
        dados.get("mp_max"),
        dados.get("ouro", 100),
        dados.get("avatar", AVATAR_PADRAO),
        atribs.get("forca", 5),
        atribs.get("defesa", 5),
        atribs.get("vitalidade", 5),
        atribs.get("agilidade", 5),
        atribs.get("inteligencia", 5),
        atribs.get("sorte", 5),
        atribs.get("carisma", 5)
    ))
    conn.commit()
    conn.close()

def carregar_jogador_db(user_id):
    conn = sqlite3.connect("terras_esquecidas.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jogadores WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0],
            "nome": row[1],
            "raca": row[2],
            "continente": row[3],
            "classe": row[4],
            "nivel": row[5],
            "xp_atual": row[6],
            "xp_max": row[7],
            "hp_atual": row[8],
            "hp_max": row[9],
            "mp_atual": row[10],
            "mp_max": row[11],
            "ouro": row[12],
            "avatar": row[13],
            "atributos_finais": {
                "forca": row[14],
                "defesa": row[15],
                "vitalidade": row[16],
                "agilidade": row[17],
                "inteligencia": row[18],
                "sorte": row[19],
                "carisma": row[20]
            }
        }
    return None

def deletar_jogador_db(user_id):
    conn = sqlite3.connect("terras_esquecidas.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jogadores WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# --- DADOS DO JOGO ---

RACAS = {
    "Humano": {
        "descricao": "+2 em todos os atributos e +10% de XP acumulado.",
        "bonus": {"forca": 2, "defesa": 2, "vitalidade": 2, "agilidade": 2, "inteligencia": 2, "sorte": 2, "carisma": 2}
    },
    "Elfo": {
        "descricao": "+4 Agilidade, +3 Inteligência, +3 Sorte.",
        "bonus": {"forca": 0, "defesa": 0, "vitalidade": 0, "agilidade": 4, "inteligencia": 3, "sorte": 3, "carisma": 0}
    },
    "Elfo Negro": {
        "descricao": "+5 Agilidade, +3 Força, +2 Sorte.",
        "bonus": {"forca": 3, "defesa": 0, "vitalidade": 0, "agilidade": 5, "inteligencia": 0, "sorte": 2, "carisma": 0}
    },
    "Anão": {
        "descricao": "+5 Defesa, +3 Vitalidade, +2 Força.",
        "bonus": {"forca": 2, "defesa": 5, "vitalidade": 3, "agilidade": 0, "inteligencia": 0, "sorte": 0, "carisma": 0}
    },
    "Draconato": {
        "descricao": "+5 Força, +3 Defesa, +2 Vitalidade.",
        "bonus": {"forca": 5, "defesa": 3, "vitalidade": 2, "agilidade": 0, "inteligencia": 0, "sorte": 0, "carisma": 0}
    },
    "Fada": {
        "descricao": "+5 Inteligência, +3 Agilidade, +2 Carisma.",
        "bonus": {"forca": 0, "defesa": 0, "vitalidade": 0, "agilidade": 3, "inteligencia": 5, "sorte": 0, "carisma": 2}
    },
    "Demônio": {
        "descricao": "+4 Força, +4 Inteligência, +2 Agilidade.",
        "bonus": {"forca": 4, "defesa": 0, "vitalidade": 0, "agilidade": 2, "inteligencia": 4, "sorte": 0, "carisma": 0}
    }
}

CONTINENTES = {
    "Orosíria": {
        "estilo": "Gótico, sombrio, névoa e mares perigosos.",
        "descricao": "Um continente insular coberto por névoas eternas. Berço da necromancia, cavaleiros corrompidos e criaturas da noite."
    },
    "Zul'Quhar": {
        "estilo": "Misticismo, deserto, oásis e tecnologia arcana.",
        "descricao": "Desertos dourados e cidades-estado erguidas sobre fontes puras de energia mágica, repleto de relíquias antigas."
    },
    "Kaelthor": {
        "estilo": "Terras selvagens, perigosas e bárbaras.",
        "descricao": "Um ambiente hostil de vulcões ativos e areia negra. Terra de sobrevivência pura, magia destrutiva e monstros colossais."
    },
    "Vaeloria": {
        "estilo": "Fantasia clássica, alta magia e impérios medievais.",
        "descricao": "O berço da civilização. Reinos prósperos, grandes castelos, florestas ancestrais e montanhas ricas dos Anões."
    }
}

CLASSES = [
    "Guerreiro", "Arqueiro", "Mago", "Druida", 
    "Cavaleiro Pesado", "Paladino", "Necromante", 
    "Clérigo", "Bruxa", "Assassino", "Monge", "Bardo"
]

ATRIBUTOS_NOME = {
    "forca": "💪 Força",
    "defesa": "🛡️ Defesa",
    "vitalidade": "❤️ Vitalidade",
    "agilidade": "⚡ Agilidade",
    "inteligencia": "🧠 Inteligência",
    "sorte": "🍀 Sorte",
    "carisma": "🎭 Carisma"
}

HABILIDADES_EQUIPADAS_PADRAO = [
    {"id": "hab_1", "nome": "🔥 Golpe Flamejante", "custo_mp": 10, "multiplicador": 1.5, "desc": "Aumenta o dano do ataque em +50%."},
    {"id": "hab_2", "nome": "⚡ Ataque Veloz", "custo_mp": 8, "multiplicador": 1.2, "desc": "Ataque rápido com chance aumentada de crítico."},
    {"id": "hab_3", "nome": "🛡️ Postura Inquebrável", "custo_mp": 12, "multiplicador": 0.8, "desc": "Causa dano e aumenta a defesa na rodada."},
    {"id": "hab_4", "nome": "💥 Impacto Arcano", "custo_mp": 15, "multiplicador": 1.8, "desc": "Libera uma explosão massiva de energia."}
]

# LISTA DOS 10 MONSTROS DA TRILHA DO SUL (FÁCIL) COM FILE_ID DO TELEGRAM
MONSTROS_SUL_FACIL = [
    {
        "nome": "🐍 Sombra das Dunas",
        "nivel": 1, "hp_max": 25, "dano": 5, "defesa": 2, "xp": 15, "ouro": 10,
        "descricao": "Uma cobra peçonhenta gigante que se esconde nas areias quentes.",
        "imagem": "AgACAgEAAxkBAAOdas3Y2xIKowpdzrk-R2z3YZM2gwMAAw1rG9sucUY7l0CFkEw-MwEAAwIAA3kAAz0E"
    },
    {
        "nome": "🦂 Escorpião Amarelo de Zul",
        "nivel": 1, "hp_max": 30, "dano": 6, "defesa": 3, "xp": 18, "ouro": 12,
        "descricao": "Dotado de ferrão venenoso e carapaça rígida.",
        "imagem": "AgACAgEAAxkBAAOgas3Zj0ispALHFnN7v0PRRsptncIAAnsMaxvxJHBGvlEK33nEbZABAAMCAAN4AAM9BA"
    },
    {
        "nome": "🐺 Chacal do Deserto",
        "nivel": 2, "hp_max": 40, "dano": 8, "defesa": 4, "xp": 25, "ouro": 15,
        "descricao": "Um predador magro e ágil que persegue aventureiros.",
        "imagem": "AgACAgEAAxkBAAOias3Zmegmf_CKJJ_E5s9AOuBoOeYAAp8MaxtQ33FGX-L3hDij6ccBAAMCAAN4AAM9BA"
    },
    {
        "nome": "🌵 Cacto Espinhoso Morto",
        "nivel": 2, "hp_max": 45, "dano": 7, "defesa": 5, "xp": 28, "ouro": 18,
        "descricao": "Planta corrompida por magia que dispara espinhos.",
        "imagem": "AgACAgEAAxkBAAOkas3ZnNDTx5ydM-RgQMv6dUYkbfwAAqAMaxtQ33FG5c-Zn84eGXYBAAMCAAN4AAM9BA"
    },
    {
        "nome": "🐜 Formiga Gigante de Areia",
        "nivel": 3, "hp_max": 55, "dano": 10, "defesa": 6, "xp": 35, "ouro": 22,
        "descricao": "Usa mandíbulas afiadas para arrastar presas.",
        "imagem": "AgACAgEAAxkBAAOmas3ZqEyOqzwCiCJrbNZCtMDohmIAAqEMaxtQ33FG__GIzahXBeABAAMCAAN4AAM9BA"
    },
    {
        "nome": "🦴 Esqueleto do Oásis Seco",
        "nivel": 3, "hp_max": 60, "dano": 11, "defesa": 5, "xp": 40, "ouro": 25,
        "descricao": "Restos mortais reanimados por necromancia.",
        "imagem": "AgACAgEAAxkBAAOnas3ZqGZkIWvpXsjPQAXjQoONaCwAAqIMaxtQ33FGuD_JZ5AQUVkBAAMCAAN5AAM9BA"
    },
    {
        "nome": "🦎 Lagarto Solar",
        "nivel": 4, "hp_max": 70, "dano": 13, "defesa": 7, "xp": 48, "ouro": 30,
        "descricao": "Absorve o calor do sol para cuspir rajadas quentes.",
        "imagem": "AgACAgEAAxkBAAOpas3ZqBkpU5Ozyfj54kOQdAysOTMAAqQMaxtQ33FGUqSJCJ3sZZUBAAMCAAN5AAM9BA"
    },
    {
        "nome": "🦅 Abutre das Ruínas",
        "nivel": 4, "hp_max": 65, "dano": 14, "defesa": 4, "xp": 50, "ouro": 32,
        "descricao": "Mergulha dos céus atacando com garras.",
        "imagem": "AgACAgEAAxkBAAOoas3ZqE3mdrSHTrdiKwQZoB-JspYAAqMMaxtQ33FGacLbqTaJJi0BAAMCAAN4AAM9BA"
    },
    {
        "nome": "🪨 Golem de Areia Solta",
        "nivel": 5, "hp_max": 85, "dano": 15, "defesa": 9, "xp": 65, "ouro": 40,
        "descricao": "Elemental pesada erguida a partir de poeira e rochas.",
        "imagem": "AgACAgEAAxkBAAOqas3ZqArM6UMAAZkcnoq1CaIVOAktAAKlDGsbUN9xRi6LVe8QFP5GAQADAgADeAADPQQ"
    },
    {
        "nome": "👤 Saqueador dos Desertos",
        "nivel": 5, "hp_max": 90, "dano": 17, "defesa": 8, "xp": 75, "ouro": 50,
        "descricao": "Mercenário armado com cimitarra veloz.",
        "imagem": "AgACAgEAAxkBAAOras3ZqC6hJoXvXRKXK9LtaYzVeJ4AAqYMaxtQ33FGEsz4LDokD1gBAAMCAAN4AAM9BA"
    }
]

# --- GERADORES DE INTERFACE E BARRAS DE STATUS ---

def gerar_barra_hp(atual, maximo, tamanho=10):
    if maximo <= 0:
        maximo = 1
    proporcao = min(max(atual / maximo, 0), 1)
    preenchido = int(round(proporcao * tamanho))
    vazio = tamanho - preenchido
    return "▬" * preenchido + "—" * vazio

def gerar_barra_mana(atual, maximo, tamanho=10):
    if maximo <= 0:
        maximo = 1
    proporcao = min(max(atual / maximo, 0), 1)
    preenchido = int(round(proporcao * tamanho))
    vazio = tamanho - preenchido
    return "◆" * preenchido + "◇" * vazio

def gerar_barra_xp(atual, maximo, tamanho=10):
    if maximo <= 0:
        maximo = 1
    proporcao = min(max(atual / maximo, 0), 1)
    preenchido = int(round(proporcao * tamanho))
    vazio = tamanho - preenchido
    porcentagem = int(proporcao * 100)
    barra = "▬" * preenchido + "—" * vazio
    return f"[{barra}] {atual}/{maximo} · {porcentagem}%"

def get_raca_keyboard():
    keyboard = []
    for raca in RACAS.keys():
        keyboard.append([
            InlineKeyboardButton(raca, callback_data=f"raca_select_{raca}"),
            InlineKeyboardButton("🔍 Ver Bônus", callback_data=f"raca_info_{raca}")
        ])
    keyboard.append([InlineKeyboardButton("⬅️ Voltar (Alterar Nome)", callback_data="voltar_nome")])
    return InlineKeyboardMarkup(keyboard)

def get_continente_keyboard():
    keyboard = []
    for cont in CONTINENTES.keys():
        keyboard.append([
            InlineKeyboardButton(cont, callback_data=f"cont_select_{cont}"),
            InlineKeyboardButton("📜 Ver História", callback_data=f"cont_info_{cont}")
        ])
    keyboard.append([InlineKeyboardButton("⬅️ Voltar (Alterar Raça)", callback_data="voltar_raca")])
    return InlineKeyboardMarkup(keyboard)

def get_classe_keyboard():
    keyboard = []
    for i in range(0, len(CLASSES), 2):
        row = [InlineKeyboardButton(CLASSES[i], callback_data=f"classe_select_{CLASSES[i]}")]
        if i + 1 < len(CLASSES):
            row.append(InlineKeyboardButton(CLASSES[i+1], callback_data=f"classe_select_{CLASSES[i+1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ Voltar (Alterar Continente)", callback_data="voltar_continente")])
    return InlineKeyboardMarkup(keyboard)

def get_menu_principal_keyboard():
    keyboard = [
        [InlineKeyboardButton("⚔️ Aventura", callback_data="menu_aventura")],
        [InlineKeyboardButton("🏰 Cidade", callback_data="menu_cidade")],
        [InlineKeyboardButton("🎒 Inventário", callback_data="menu_inventario"),
         InlineKeyboardButton("👤 Meu Personagem", callback_data="menu_personagem")],
        [InlineKeyboardButton("🛡️ Clã", callback_data="menu_cla"),
         InlineKeyboardButton("🎉 Eventos", callback_data="menu_eventos")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_menu_aventura_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🗺️ Trilhas", callback_data="aventura_trilhas"),
            InlineKeyboardButton("🏹 Caçada", callback_data="aventura_cacada")
        ],
        [
            InlineKeyboardButton("🏰 Masmorra", callback_data="aventura_masmorra"),
            InlineKeyboardButton("⛵ Viagem", callback_data="aventura_viagem")
        ],
        [
            InlineKeyboardButton("🔙 Menu Principal", callback_data="voltar_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_menu_trilhas_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🏜️ Trilha do Sul", callback_data="trilha_selecionar_Sul"),
            InlineKeyboardButton("❄️ Trilha do Norte", callback_data="trilha_selecionar_Norte")
        ],
        [
            InlineKeyboardButton("🌲 Trilha do Leste", callback_data="trilha_selecionar_Leste"),
            InlineKeyboardButton("⛰️ Trilha do Oeste", callback_data="trilha_selecionar_Oeste")
        ],
        [
            InlineKeyboardButton("⬅️ Voltar para Aventura", callback_data="menu_aventura")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_dificuldade_trilha_keyboard(trilha_nome):
    keyboard = [
        [InlineKeyboardButton("🟢 Fácil", callback_data=f"iniciartrilha_{trilha_nome}_Facil")],
        [InlineKeyboardButton("🟡 Normal", callback_data=f"iniciartrilha_{trilha_nome}_Normal")],
        [InlineKeyboardButton("🟠 Difícil", callback_data=f"iniciartrilha_{trilha_nome}_Dificil")],
        [InlineKeyboardButton("🔴 Extremo", callback_data=f"iniciartrilha_{trilha_nome}_Extremo")],
        [InlineKeyboardButton("💀 Inferno", callback_data=f"iniciartrilha_{trilha_nome}_Inferno")],
        [InlineKeyboardButton("⬅️ Voltar às Trilhas", callback_data="aventura_trilhas")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_combate_encontro_keyboard(trilha_nome):
    keyboard = [
        [InlineKeyboardButton("⚔️ Atacar", callback_data="combate_atacar"), InlineKeyboardButton("🛡️ Defender", callback_data="combate_defender")],
        [InlineKeyboardButton("🎒 Usar Item", callback_data="combate_usar_item"), InlineKeyboardButton("✨ Habilidades", callback_data="combate_habilidades")],
        [InlineKeyboardButton("🏃 Fugir", callback_data=f"trilha_selecionar_{trilha_nome}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_habilidades_keyboard():
    keyboard = []
    for hab in HABILIDADES_EQUIPADAS_PADRAO:
        keyboard.append([InlineKeyboardButton(f"{hab['nome']} (💧{hab['custo_mp']} MP)", callback_data=f"usar_hab_{hab['id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Voltar ao Combate", callback_data="voltar_combate_menu")])
    return InlineKeyboardMarkup(keyboard)

# --- COMANDOS AUXILIARES ---

async def comando_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    titulo = chat.title or "Chat Privado"
    tipo = chat.type
    chat_id = chat.id

    if chat.type in ["group", "supergroup", "channel"]:
        registrar_chat_db(chat_id, titulo, tipo)
        msg = f"🏰 **REGISTRO DE COMUNIDADE**\n\n📌 **Título:** {escapar_markdown(titulo)}\n🆔 **ID:** `{chat_id}`"
    else:
        msg = f"👤 **Seu ID Privado:** `{chat_id}`"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def comando_comunidades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chats = listar_chats_db()
    if not chats:
        await update.message.reply_text("📜 Nenhuma comunidade registrada ainda.")
        return
    texto = "🏰 **GRUPOS REGISTRADOS:**\n"
    for cid, tit, tip, tid in chats:
        texto += f"• **{escapar_markdown(tit)}** (`{cid}`)\n"
    await update.message.reply_text(texto, parse_mode="Markdown")

async def comando_set_masmorra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    message = update.effective_message
    if chat.type in ["supergroup", "group"]:
        thread_id = getattr(message, 'message_thread_id', None)
        conn = sqlite3.connect("terras_esquecidas.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chats_comunidade (chat_id, titulo, tipo, masmorra_thread_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET masmorra_thread_id = ?, titulo = ?, tipo = ?
        """, (chat.id, chat.title, chat.type, thread_id, thread_id, chat.title, chat.type))
        conn.commit()
        conn.close()
        await message.reply_text("🏰 Tópico/Grupo vinculado com sucesso!", parse_mode="Markdown")
    else:
        await message.reply_text("❌ Comando apenas para grupos.")

async def monitorar_membro_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if result and result.new_chat_member.status in ["member", "administrator"]:
        chat = result.chat
        registrar_chat_db(chat.id, chat.title, chat.type)

# --- FLUXO DE CRIAÇÃO DE PERSONAGEM (CONVERSATION HANDLER) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    user_id = user.id
    chat = update.effective_chat

    if chat.type in ["group", "supergroup"]:
        registrar_chat_db(chat.id, chat.title, chat.type)

    context.user_data.clear()
    jogador = carregar_jogador_db(user_id)
    if jogador:
        context.user_data.update(jogador)
        await enviar_menu_interface(update, context)
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton("⚔️ Criar Personagem", callback_data="criar_personagem")]]
    await update.message.reply_text(
        f"🏰 **Bem-vindo às Terras Esquecidas, {escapar_markdown(user.first_name)}!**\n\nCrie seu herói para iniciar:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return NOME

async def iniciar_criacao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass
    await query.edit_message_text("✍️ **Digite o nome do seu personagem:**", parse_mode="Markdown")
    return NOME

async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        nome = update.message.text.strip()
        context.user_data["nome"] = nome
        await update.message.reply_text(
            f"👤 Excelente, **{escapar_markdown(nome)}**!\n\nEscolha a sua 🧬 **Raça**:",
            reply_markup=get_raca_keyboard(),
            parse_mode="Markdown"
        )
    else:
        query = update.callback_query
        if query:
            try:
                await query.answer()
            except Exception:
                pass
        await query.edit_message_text(
            "Escolha a sua 🧬 **Raça**:",
            reply_markup=get_raca_keyboard(),
            parse_mode="Markdown"
        )
    return RACA

async def escolher_raca(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    data = query.data
    if data.startswith("raca_info_"):
        raca_nome = data.replace("raca_info_", "")
        desc = RACAS[raca_nome]["descricao"]
        try:
            await query.answer(f"✨ {raca_nome}: {desc}", show_alert=True)
        except Exception:
            pass
        return RACA

    if data == "voltar_nome":
        await query.edit_message_text("✍️ **Digite o novo nome para o seu personagem:**", parse_mode="Markdown")
        return NOME

    raca_escolhida = data.replace("raca_select_", "")
    context.user_data["raca"] = raca_escolhida

    await query.edit_message_text(
        f"🧬 **Raça:** {escapar_markdown(raca_escolhida)}\n\n🌍 Escolha o **Continente de Origem**:",
        reply_markup=get_continente_keyboard(),
        parse_mode="Markdown"
    )
    return CONTINENTE

async def escolher_continente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    data = query.data
    if data.startswith("cont_info_"):
        cont_nome = data.replace("cont_info_", "")
        info = CONTINENTES[cont_nome]
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="voltar_continentes_lista")]]
        await query.edit_message_text(
            f"🏛️ **{escapar_markdown(cont_nome)}**\n\n📜 {escapar_markdown(info['descricao'])}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return CONTINENTE

    if data == "voltar_continentes_lista":
        await query.edit_message_text("🌍 Escolha o **Continente de Origem**:", reply_markup=get_continente_keyboard(), parse_mode="Markdown")
        return CONTINENTE

    if data == "voltar_raca":
        return await receber_nome(update, context)

    cont_escolhido = data.replace("cont_select_", "")
    context.user_data["continente"] = cont_escolhido

    await query.edit_message_text(
        f"🗺️ **Origem:** {escapar_markdown(cont_escolhido)}\n\n⚔️ Escolha a sua **Classe** de combate:",
        reply_markup=get_classe_keyboard(),
        parse_mode="Markdown"
    )
    return CLASSE

async def escolher_classe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    data = query.data
    if data == "voltar_continente":
        await query.edit_message_text("🌍 Escolha o **Continente de Origem**:", reply_markup=get_continente_keyboard(), parse_mode="Markdown")
        return CONTINENTE

    classe_escolhida = data.replace("classe_select_", "")
    context.user_data["classe"] = classe_escolhida
    context.user_data["pontos_livres"] = 10
    context.user_data["atributos"] = {"forca": 5, "defesa": 5, "vitalidade": 5, "agilidade": 5, "inteligencia": 5, "sorte": 5, "carisma": 5}

    return await renderizar_atributos(query, context)

async def renderizar_atributos(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    atributos = context.user_data.get("atributos")
    pontos = context.user_data.get("pontos_livres", 10)

    keyboard = []
    for key, label in ATRIBUTOS_NOME.items():
        keyboard.append([
            InlineKeyboardButton("➖", callback_data=f"rem_{key}"),
            InlineKeyboardButton(f"{label}: {atributos[key]}", callback_data="noop"),
            InlineKeyboardButton("➕", callback_data=f"add_{key}")
        ])

    if pontos == 0:
        keyboard.append([InlineKeyboardButton("➡️ Avançar (Escolher Foto)", callback_data="confirmar_ficha")])
    keyboard.append([InlineKeyboardButton("⬅️ Voltar (Alterar Classe)", callback_data="voltar_classe")])

    texto = f"📊 **DISTRIBUIÇÃO DE ATRIBUTOS**\n\n🎯 **Pontos Restantes:** `{pontos}`"
    try:
        await query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise e
    return ATRIBUTOS

async def manipular_atributos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    action = query.data
    if action == "noop":
        return ATRIBUTOS

    if action == "voltar_classe":
        await query.edit_message_text("⚔️ Escolha a sua **Classe**:", reply_markup=get_classe_keyboard(), parse_mode="Markdown")
        return CLASSE

    pontos = context.user_data.get("pontos_livres", 10)
    atributos = context.user_data.get("atributos")

    if action.startswith("add_"):
        attr = action.replace("add_", "")
        if pontos > 0:
            atributos[attr] += 1
            context.user_data["pontos_livres"] -= 1
    elif action.startswith("rem_"):
        attr = action.replace("rem_", "")
        if atributos[attr] > 5:
            atributos[attr] -= 1
            context.user_data["pontos_livres"] += 1
    elif action == "confirmar_ficha":
        if pontos == 0:
            keyboard = [[InlineKeyboardButton("⏭️ Pular / Usar Imagem Padrão", callback_data="pular_avatar")]]
            await query.edit_message_text("🖼️ Envie uma foto para definir sua aparência ou use o padrão:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return AVATAR

    return await renderizar_atributos(query, context)

async def receber_avatar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message and update.message.photo:
        file_id = update.message.photo[-1].file_id
        context.user_data["avatar"] = file_id
        await update.message.reply_text(f"📷 **Foto recebida!**\n\n🆔 `File ID`: `{file_id}`", parse_mode="Markdown")
    else:
        context.user_data["avatar"] = AVATAR_PADRAO
    return await finalizar_personagem(update, context)

async def pegar_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.photo:
        file_id = update.message.photo[-1].file_id
        await update.message.reply_text(
            f"🖼️ **IMAGEM DETECTADA!**\n\n🆔 **File ID:**\n`{file_id}`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Envie uma foto acompanhada da legenda `/fileid`.", parse_mode="Markdown")

async def pular_avatar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass
    context.user_data["avatar"] = AVATAR_PADRAO
    return await finalizar_personagem(update, context)

async def finalizar_personagem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    raca = context.user_data.get("raca", "Humano")
    atributos_distribuidos = context.user_data.get("atributos", {})
    bonus_raca = RACAS.get(raca, {}).get("bonus", {})

    atributos_finais = {attr: atributos_distribuidos.get(attr, 5) + bonus_raca.get(attr, 0) for attr in ATRIBUTOS_NOME.keys()}
    context.user_data["atributos_finais"] = atributos_finais
    context.user_data["hp_max"] = atributos_finais["vitalidade"] * 20
    context.user_data["hp_atual"] = context.user_data["hp_max"]
    context.user_data["mp_max"] = atributos_finais["inteligencia"] * 10
    context.user_data["mp_atual"] = context.user_data["mp_max"]
    context.user_data["xp_atual"] = 0
    context.user_data["xp_max"] = 100
    context.user_data["ouro"] = 100
    context.user_data["nivel"] = 1

    salvar_jogador_db(user_id, context.user_data)
    await enviar_menu_interface(update, context, chat_id=update.effective_chat.id)
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Ação cancelada.")
    return ConversationHandler.END

# --- NAVEGAÇÃO DOS MENUS E COMBATE ---

async def enviar_menu_interface(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id=None):
    user_id = update.effective_user.id
    dados = carregar_jogador_db(user_id)
    if not dados:
        return

    context.user_data.update(dados)
    hp_barra = gerar_barra_hp(dados.get("hp_atual"), dados.get("hp_max"))
    mp_barra = gerar_barra_mana(dados.get("mp_atual"), dados.get("mp_max"))
    xp_barra = gerar_barra_xp(dados.get("xp_atual"), dados.get("xp_max"))

    texto = (
        f"👑 **{escapar_markdown(dados.get('nome'))}** — _Nível {dados.get('nivel', 1)}_\n"
        f"🧬 **Raça:** {escapar_markdown(dados.get('raca'))} | 🛡️ **Classe:** {escapar_markdown(dados.get('classe'))}\n\n"
        f"**XP** `{xp_barra}`\n\n"
        f"❤️ **HP** `{hp_barra}` `{dados.get('hp_atual')}/{dados.get('hp_max')}`\n"
        f"🔷 **Mana** `{mp_barra}` `{dados.get('mp_atual')}/{dados.get('mp_max')}`\n\n"
        f"🏰 **MENU PRINCIPAL**"
    )
    cid = chat_id if chat_id else update.effective_chat.id
    await context.bot.send_photo(chat_id=cid, photo=dados.get("avatar", AVATAR_PADRAO), caption=texto, reply_markup=get_menu_principal_keyboard(), parse_mode="Markdown")

async def menu_principal_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if not carregar_jogador_db(update.effective_user.id):
        await update.message.reply_text("❌ Crie um personagem primeiro com /start.")
        return
    await enviar_menu_interface(update, context)

async def renderizar_tela_combate(query, context, mensagem_log=""):
    monstro = context.user_data.get("monstro_atual")
    trilha_nome = context.user_data.get("trilha_atual", "Sul")
    if not monstro:
        return

    hp_m = gerar_barra_hp(monstro["hp_atual"], monstro["hp_max"])
    dados = carregar_jogador_db(query.from_user.id)
    hp_p = gerar_barra_hp(dados.get("hp_atual"), dados.get("hp_max"))
    mp_p = gerar_barra_mana(dados.get("mp_atual"), dados.get("mp_max"))

    texto = (
        f"⚔️ **COMBATE — TRILHA DO {trilha_nome.upper()}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👾 **{monstro['nome']}** _(Nível {monstro['nivel']})_\n"
        f"❤️ **HP Monstro:** `{hp_m}` `{monstro['hp_atual']}/{monstro['hp_max']}`\n\n"
        f"👤 **{escapar_markdown(dados.get('nome'))}**\n"
        f"❤️ **HP:** `{hp_p}` `{dados.get('hp_atual')}/{dados.get('hp_max')}`\n"
        f"🔷 **MP:** `{mp_p}` `{dados.get('mp_atual')}/{dados.get('mp_max')}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    if mensagem_log:
        texto += f"📜 {mensagem_log}\n━━━━━━━━━━━━━━━━━━━━━━━\n"

    try:
        await query.edit_message_media(
            media=InputMediaPhoto(media=monstro["imagem"], caption=texto, parse_mode="Markdown"),
            reply_markup=get_combate_encontro_keyboard(trilha_nome)
        )
    except Exception:
        await query.edit_message_caption(caption=texto, reply_markup=get_combate_encontro_keyboard(trilha_nome), parse_mode="Markdown")

async def tratar_menu_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    acao = query.data
    if acao.startswith("add_") or acao.startswith("rem_") or acao in ["noop", "confirmar_ficha", "voltar_classe"]:
        return

    try:
        await query.answer()
    except Exception:
        pass

    user_id = update.effective_user.id
    dados = carregar_jogador_db(user_id)
    if not dados and acao != "deletar_conta_final":
        return

    if acao == "menu_aventura":
        await query.edit_message_caption(caption="⚔️ **MUNDO DE AVENTURA**", reply_markup=get_menu_aventura_keyboard(), parse_mode="Markdown")
    elif acao == "aventura_trilhas":
        await query.edit_message_caption(caption="🗺️ **CENTRAL DE TRILHAS**", reply_markup=get_menu_trilhas_keyboard(), parse_mode="Markdown")
    elif acao.startswith("trilha_selecionar_"):
        trilha_nome = acao.replace("trilha_selecionar_", "")
        context.user_data["trilha_atual"] = trilha_nome
        await query.edit_message_caption(caption=f"🗺️ **TRILHA DO {trilha_nome.upper()}**\nEscolha a dificuldade:", reply_markup=get_dificuldade_trilha_keyboard(trilha_nome), parse_mode="Markdown")
    elif acao.startswith("iniciartrilha_"):
        partes = acao.replace("iniciartrilha_", "").split("_")
        trilha_nome, dificuldade = partes[0], partes[1]
        if dificuldade.lower() == "facil":
            monstro = random.choice(MONSTROS_SUL_FACIL).copy()
            monstro["hp_atual"] = monstro["hp_max"]
            context.user_data["monstro_atual"] = monstro
            context.user_data["trilha_atual"] = trilha_nome
            
            hp_m = gerar_barra_hp(monstro["hp_max"], monstro["hp_max"])
            hp_p = gerar_barra_hp(dados.get("hp_atual"), dados.get("hp_max"))
            mp_p = gerar_barra_mana(dados.get("mp_atual"), dados.get("mp_max"))
            
            texto = (
                f"⚔️ **COMBATE — TRILHA DO {trilha_nome.upper()}**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👾 **{monstro['nome']}** _(Nível {monstro['nivel']})_\n"
                f"❤️ **HP Monstro:** `{hp_m}` `{monstro['hp_max']}/{monstro['hp_max']}`\n\n"
                f"👤 **{escapar_markdown(dados.get('nome'))}**\n"
                f"❤️ **HP:** `{hp_p}` `{dados.get('hp_atual')}/{dados.get('hp_max')}`\n"
                f"🔷 **MP:** `{mp_p}` `{dados.get('mp_atual')}/{dados.get('mp_max')}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📜 Você encontrou um {monstro['nome']}!\n━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=monstro["imagem"],
                caption=texto,
                reply_markup=get_combate_encontro_keyboard(trilha_nome),
                parse_mode="Markdown"
            )
            try:
                await query.message.delete()
            except Exception:
                pass
            return
        else:
            await query.answer(f"⚠️ A dificuldade {dificuldade} estará disponível em breve!", show_alert=True)
            return
    elif acao == "combate_atacar":
        monstro = context.user_data.get("monstro_atual")
        if not monstro:
            return
        atribs = dados.get("atributos_finais", {})
        is_magico = dados.get("classe") in ["Mago", "Bruxa", "Necromante", "Clérigo", "Druida"]
        dano_base = atribs.get("inteligencia", 5) if is_magico else atribs.get("forca", 5)
        
        if random.uniform(0, 100) < (atribs.get("agilidade", 5) * 0.5):
            msg = f"O {monstro['nome']} esquivou!"
        else:
            is_crit = random.uniform(0, 100) < (atribs.get("sorte", 5) * 0.5)
            dano = max(1, int((dano_base * (1.5 if is_crit else 1.0)) - monstro["defesa"]))
            monstro["hp_atual"] = max(0, monstro["hp_atual"] - dano)
            msg = f"{'💥 **CRÍTICO!** ' if is_crit else ''}Causou `{dano}` de dano!"

        if monstro["hp_atual"] <= 0:
            trilha_atual = context.user_data.get("trilha_atual", "Sul")
            dados["xp_atual"] += monstro["xp"]
            dados["ouro"] += monstro["ouro"]
            salvar_jogador_db(user_id, dados)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Procurar Outro Monstro", callback_data=f"iniciartrilha_{trilha_atual}_Facil")],
                [InlineKeyboardButton("⬅️ Voltar às Dificuldades", callback_data=f"trilha_selecionar_{trilha_atual}")]
            ])
            await query.edit_message_caption(caption=f"🎉 **VITÓRIA!**\n+{monstro['xp']} XP | +{monstro['ouro']} Ouro", reply_markup=keyboard, parse_mode="Markdown")
            return

        dano_m = max(1, monstro["dano"] - int(atribs.get("defesa", 5) * 0.5))
        dados["hp_atual"] = max(0, dados.get("hp_atual", 100) - dano_m)
        salvar_jogador_db(user_id, dados)
        msg += f"\n😈 O monstro causou `{dano_m}` de dano."
        await renderizar_tela_combate(query, context, msg)
    elif acao == "combate_defender":
        monstro = context.user_data.get("monstro_atual")
        dano_m = max(1, int(monstro["dano"] * 0.3))
        dados["hp_atual"] = max(0, dados.get("hp_atual", 100) - dano_m)
        salvar_jogador_db(user_id, dados)
        await renderizar_tela_combate(query, context, f"🛡️ Defesa assumida! Recebeu `{dano_m}` de dano.")
    elif acao == "combate_habilidades":
        await query.edit_message_caption(caption="✨ **HABILIDADES EQUIPADAS**", reply_markup=get_habilidades_keyboard(), parse_mode="Markdown")
    elif acao.startswith("usar_hab_"):
        hab_id = acao.replace("usar_hab_", "")
        hab = next((h for h in HABILIDADES_EQUIPADAS_PADRAO if h["id"] == hab_id), None)
        monstro = context.user_data.get("monstro_atual")
        if hab and monstro:
            if dados.get("mp_atual", 0) < hab["custo_mp"]:
                await query.answer("⚠️ Mana insuficiente!", show_alert=True)
                return
            dados["mp_atual"] -= hab["custo_mp"]
            atribs = dados.get("atributos_finais", {})
            dano_base = atribs.get("inteligencia", 5) if dados.get("classe") in ["Mago", "Bruxa", "Necromante", "Clérigo", "Druida"] else atribs.get("forca", 5)
            dano = max(1, int((dano_base * hab["multiplicador"]) - monstro["defesa"]))
            monstro["hp_atual"] = max(0, monstro["hp_atual"] - dano)
            
            if monstro["hp_atual"] <= 0:
                trilha_atual = context.user_data.get("trilha_atual", "Sul")
                dados["xp_atual"] += monstro["xp"]
                dados["ouro"] += monstro["ouro"]
                salvar_jogador_db(user_id, dados)
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Procurar Outro Monstro", callback_data=f"iniciartrilha_{trilha_atual}_Facil")],
                    [InlineKeyboardButton("⬅️ Voltar às Dificuldades", callback_data=f"trilha_selecionar_{trilha_atual}")]
                ])
                await query.edit_message_caption(caption=f"🎉 **VITÓRIA!**\n+{monstro['xp']} XP | +{monstro['ouro']} Ouro", reply_markup=keyboard, parse_mode="Markdown")
                return

            dano_m = max(1, monstro["dano"] - int(atribs.get("defesa", 5) * 0.5))
            dados["hp_atual"] = max(0, dados.get("hp_atual", 100) - dano_m)
            salvar_jogador_db(user_id, dados)

            msg = f"✨ Usou {hab['nome']} ({dano} dano).\n😈 O monstro contra-atacou causando `{dano_m}` de dano."
            await renderizar_tela_combate(query, context, msg)
    elif acao == "voltar_combate_menu":
        await renderizar_tela_combate(query, context)
    elif acao == "menu_cidade":
        await query.edit_message_caption(caption="🏰 **CIDADE PRINCIPAL**\n(Em breve)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")]]), parse_mode="Markdown")
    elif acao == "menu_inventario":
        await query.edit_message_caption(caption=f"🎒 **INVENTÁRIO**\n💰 Ouro: `{dados.get('ouro', 0)}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")]]), parse_mode="Markdown")
    elif acao == "menu_personagem":
        atribs = dados.get("atributos_finais", {})
        esquiva = atribs.get("agilidade", 5) * 0.5
        critico = atribs.get("sorte", 5) * 0.5
        texto = (
            f"📜 **FICHA DE {escapar_markdown(dados.get('nome'))}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👑 Nível: `{dados.get('nivel')}` | 💰 Ouro: `{dados.get('ouro')}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• 💪 Força: `{atribs.get('forca')}`\n"
            f"• 🛡️ Defesa: `{atribs.get('defesa')}`\n"
            f"• ❤️ Vitalidade: `{atribs.get('vitalidade')}`\n"
            f"• ⚡ Agilidade: `{atribs.get('agilidade')}`\n"
            f"• 🧠 Inteligência: `{atribs.get('inteligencia')}`\n"
            f"• 🍀 Sorte: `{atribs.get('sorte')}`\n"
            f"• 🎭 Carisma: `{atribs.get('carisma')}`\n\n"
            f"✨ Esquiva: `{esquiva}%` | 💥 Crítico: `{critico}%`"
        )
        await query.edit_message_caption(caption=texto, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")]]), parse_mode="Markdown")
    elif acao == "voltar_menu":
        await enviar_menu_interface(update, context)
        try:
            await query.message.delete()
        except Exception:
            pass

# --- INICIALIZAÇÃO DO BOT ---

def main():
    TOKEN = "8717356763:AAHRHCMdMcTy4GONg1_MW7VTFo51yAm9qKU"
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NOME: [CallbackQueryHandler(iniciar_criacao, pattern="^criar_personagem$"), MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
            RACA: [CallbackQueryHandler(escolher_raca)],
            CONTINENTE: [CallbackQueryHandler(escolher_continente)],
            CLASSE: [CallbackQueryHandler(escolher_classe)],
            ATRIBUTOS: [CallbackQueryHandler(manipular_atributos)],
            AVATAR: [MessageHandler(filters.PHOTO, receber_avatar), CallbackQueryHandler(pular_avatar, pattern="^pular_avatar$")],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        name="criacao_personagem_conv",
        persistent=False,
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("id", comando_id))
    application.add_handler(CommandHandler("comunidades", comando_comunidades))
    application.add_handler(CommandHandler("set_masmorra", comando_set_masmorra))
    application.add_handler(CommandHandler("fileid", pegar_file_id))
    application.add_handler(ChatMemberHandler(monitorar_membro_chat, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(CommandHandler("menu", menu_principal_comando))
    application.add_handler(CallbackQueryHandler(tratar_menu_global))

    print("🗡️ Bot Terras Esquecidas Completo Ativo!")
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
