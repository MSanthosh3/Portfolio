"""
Portfolio Website Backend — Santhosh M
Flask app with rule-based chatbot, visitor tracking, and analytics dashboard.
No external API keys required. Fully self-contained.
"""

import os
import re
import random
import sqlite3
from datetime import datetime

from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for, send_from_directory
)
from rapidfuzz import fuzz
from dotenv import load_dotenv

# ─── Configuration ──────────────────────────────────────────────
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-fallback-secret-change-in-production')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'analytics.db')
MAX_MESSAGE_LENGTH = 500
CONFIDENCE_THRESHOLD = 65


# ─── Database Layer ─────────────────────────────────────────────

def get_db():
    """Get a database connection with Row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables if they don't exist."""
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS visitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            user_agent TEXT,
            timestamp TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


def get_real_ip():
    """Extract real client IP, accounting for Railway's reverse proxy."""
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'


def parse_user_agent(ua_string):
    """Parse browser and OS from user-agent string."""
    if not ua_string:
        return 'Unknown'

    browser = 'Unknown'
    os_name = 'Unknown'

    # Browser detection (order matters)
    if 'Edg/' in ua_string or 'Edge/' in ua_string:
        browser = 'Edge'
    elif 'OPR/' in ua_string or 'Opera/' in ua_string:
        browser = 'Opera'
    elif 'Chrome/' in ua_string:
        browser = 'Chrome'
    elif 'Firefox/' in ua_string:
        browser = 'Firefox'
    elif 'Safari/' in ua_string:
        browser = 'Safari'
    elif 'bot' in ua_string.lower() or 'crawl' in ua_string.lower():
        browser = 'Bot'

    # OS detection
    if 'Windows' in ua_string:
        os_name = 'Windows'
    elif 'iPhone' in ua_string:
        os_name = 'iOS'
    elif 'iPad' in ua_string:
        os_name = 'iPadOS'
    elif 'Android' in ua_string:
        os_name = 'Android'
    elif 'Macintosh' in ua_string or 'Mac OS' in ua_string:
        os_name = 'macOS'
    elif 'Linux' in ua_string:
        os_name = 'Linux'

    return f'{browser} / {os_name}'


# ─── Chatbot Knowledge Base ────────────────────────────────────
# ── CUSTOMIZE: Update these responses with your own details ────

KNOWLEDGE_BASE = {
    'greeting': {
        'triggers': [
            'hello', 'hi', 'hey', 'good morning', 'good evening',
            'howdy', 'greetings', 'whats up', 'sup', 'yo'
        ],
        'responses': [
            "Hey there! 👋 I'm Santhosh's portfolio bot. Ask me about his skills, projects, or experience!",
            "Hello! Welcome to Santhosh M's portfolio. What would you like to know — projects, skills, or experience?",
            "Hi! 🚀 Great to have you here. Feel free to ask about Santhosh's AI/ML work, projects, or background!"
        ]
    },
    'bio': {
        'triggers': [
            'who is santhosh', 'tell me about santhosh', 'about you',
            'who are you', 'about santhosh', 'introduce yourself',
            'about him', 'biography', 'background', 'tell me about yourself'
        ],
        'responses': [
            "Santhosh M is an AI/ML Engineer based in Salem, Tamil Nadu 🇮🇳. He specializes in production-grade Generative AI systems, RAG pipelines, LLM fine-tuning, and multi-agent architectures. He's worked on cutting AI hallucination rates and building scalable retrieval systems across multiple domains!",
            "Santhosh M is an AI/ML Engineer from Salem, India, passionate about building real-world AI systems. From fine-tuning LLMs to creating production RAG pipelines, he bridges the gap between cutting-edge AI research and deployment.",
            "Meet Santhosh M — an AI/ML Engineer who builds production-grade GenAI systems. His expertise spans RAG pipelines, LLM fine-tuning (QLoRA/LoRA), and multi-agent architectures, with real-world impact across multiple industries."
        ]
    },
    'skills': {
        'triggers': [
            'what are your skills', 'skills', 'technologies', 'what do you know',
            'tech stack', 'what can you do', 'programming languages',
            'tools', 'frameworks', 'expertise', 'competencies'
        ],
        'responses': [
            "🤖 AI/ML: LLMs, GenAI, RAG, QLoRA/LoRA, NLP, NER, spaCy\n⚡ Frameworks: LangChain, HuggingFace, PyTorch, FastAPI\n🗄️ Databases: Milvus, Neo4j, PostgreSQL, ChromaDB\n☁️ Cloud: Docker, HF Spaces, Render, GitHub Actions\n💻 Languages: Python, PHP, SQL, Laravel",
            "Santhosh works with a modern AI/ML stack — LangChain, HuggingFace, PyTorch for models; Milvus, Neo4j, ChromaDB for vector/graph databases; Docker and GitHub Actions for deployment. He's proficient in Python, SQL, and FastAPI too!",
            "Core stack: LLMs & GenAI (LangChain, HuggingFace, PEFT, TRL), vector DBs (Milvus, ChromaDB), graph DBs (Neo4j), cloud (Docker, Render, GitHub Actions), and languages (Python, SQL, PHP). Full-spectrum AI/ML engineer!"
        ]
    },
    'projects': {
        'triggers': [
            'projects', 'what have you built', 'portfolio', 'your work',
            'show me projects', 'what projects', 'works', 'creations',
            'things you built', 'applications you made'
        ],
        'responses': [
            "🏏 CricBot IPL — Fine-tuned TinyLlama on 17 yrs of IPL data\n🔍 Multi-Source Retrieval Agent — LangChain + Tavily + Claude\n📊 Neo4j QA System — Graph-augmented QA pipeline\n⚙️ ML Suite — Classification, regression, clustering + GUI\nScroll down to see them all!",
            "Santhosh's projects span AI/ML and sports analytics. Highlights: CricBot IPL (fine-tuned LLM on IPL data), Multi-Source Retrieval Agent (LangChain + Claude), Neo4j QA System, and ML Deployment suite. Check the Projects section below! 👇",
            "From fine-tuning LLMs for cricket analytics (CricBot IPL) to building production RAG systems that cut hallucination by 40% — Santhosh's projects showcase real-world AI engineering. See the Projects section for details!"
        ]
    },
    'cricbot': {
        'triggers': [
            'cricbot', 'cricket', 'ipl', 'cricket bot', 'cricket chatbot',
            'ipl chatbot', 'cricbot ipl', 'tinyllama', 'cricket project'
        ],
        'responses': [
            "🏏 CricBot IPL is Santhosh's flagship project! Fine-tuned TinyLlama-1.1B on 17 years of IPL data using QLoRA/PEFT. Features: Milvus Lite vector retrieval, Wikipedia fallback, spaCy NER session memory, franchise-themed UI, zero-cost hosting!",
            "CricBot IPL — an AI cricket chatbot fine-tuned on 17 years of IPL data. Tech: TinyLlama-1.1B (QLoRA), Milvus Lite retrieval, spaCy NER, Wikipedia fallback. All hosted at zero cost! 🏏",
            "The CricBot project showcases LLM fine-tuning at its best — TinyLlama-1.1B trained on 17 years of IPL data, with Milvus-powered retrieval, spaCy NER for entity recognition, and a franchise-themed UI."
        ]
    },
    'rag_system': {
        'triggers': [
            'rag', 'rag pipeline', 'rag system', 'retrieval augmented',
            'hallucination', 'chromadb', 'vector grounding', 'rag project',
            'reduce hallucination', 'semantic search'
        ],
        'responses': [
            "🔬 At LezdotechMed, Santhosh built a production RAG system using ChromaDB and multiple LLMs — cutting hallucination by 40% through semantic vector grounding. A flagship example of reliable AI in production!",
            "One of Santhosh's key achievements: a multi-LLM RAG pipeline with ChromaDB that reduced hallucination rates by 40%. Built and deployed in production at LezdotechMed.",
            "Santhosh built a production-grade RAG pipeline at LezdotechMed — ChromaDB for semantic retrieval, multiple LLMs for synthesis. Result: 40% reduction in AI hallucination. Real impact, real scale!"
        ]
    },
    'experience': {
        'triggers': [
            'experience', 'work experience', 'where do you work',
            'job', 'career', 'employment', 'work history',
            'companies', 'lezdotechmed', 'giggso', 'professional'
        ],
        'responses': [
            "🔬 AI Developer @ LezdotechMed (Oct 2024 – Present)\n• Production RAG systems — reduced hallucination by 40%\n• Multi-source retrieval agents with Claude as reasoning engine\n• Neo4j-backed QA audit pipeline\n\n📊 ML Intern @ Giggso (Jul – Sep 2024)\n• Scikit-learn models with real-time GUI\n• NLP on Amazon product reviews",
            "Santhosh currently works as an AI Developer at LezdotechMed in Salem, building production RAG systems and multi-agent retrieval pipelines. Previously, he was an ML Intern at Giggso in Chennai, working on classification models and NLP.",
            "Two roles shaped Santhosh's career: AI Developer at LezdotechMed (building RAG systems, retrieval agents with Claude, Neo4j pipelines — 40% hallucination reduction) and ML Intern at Giggso (Scikit-learn models, NLP analysis)."
        ]
    },
    'education': {
        'triggers': [
            'education', 'where did you study', 'university', 'college',
            'degree', 'academic', 'qualification', 'school',
            'geology', 'mphil', 'msc'
        ],
        'responses': [
            "🎓 M.Phil in Applied Geology — Govt Arts College, Salem (2019–2022)\n📚 M.Sc in Applied Geology — Govt Arts College, Salem (2017–2019)\n\nFun fact: He transitioned from geology to AI/ML — quite a career pivot! 🌍➡️🤖",
            "Santhosh holds M.Phil & M.Sc degrees in Applied Geology from Government Arts College, Salem. His unique transition from earth sciences to AI/ML gives him a distinctive perspective in problem-solving!",
            "Academically — M.Phil (2019–2022) and M.Sc (2017–2019) in Applied Geology from Govt Arts College, Salem. His geology-to-AI career pivot showcases impressive adaptability! 🎓"
        ]
    },
    'publications': {
        'triggers': [
            'publication', 'publications', 'research paper', 'paper',
            'journal', 'published', 'groundwater', 'geospatial', 'article'
        ],
        'responses': [
            "📜 Santhosh published a peer-reviewed research paper titled 'Demarcation of Groundwater Potential Zones Using Geospatial Technology in Edappadi Block, Salem District, Tamil Nadu, India' in the International Journal of Geography and Geology (2021).\nLink: https://archive.conscientiabeam.com/index.php/10/article/view/1711",
            "Yes! During his M.Phil, Santhosh published research in the International Journal of Geography and Geology (2021) on groundwater potential zones demarcation using ArcGIS and remote sensing: https://archive.conscientiabeam.com/index.php/10/article/view/1711",
            "Santhosh has a published paper: 'Demarcation of Groundwater Potential Zones Using Geospatial Technology in Edappadi Block, Salem District' (2021). You can read it here: https://archive.conscientiabeam.com/index.php/10/article/view/1711"
        ]
    },
    'certifications': {
        'triggers': [
            'certifications', 'certificates', 'certified',
            'oracle', 'salesforce', 'nanodegree', 'credentials'
        ],
        'responses': [
            "📜 Certifications:\n• Generative AI Certified Professional — Oracle\n• Salesforce AI Associate — Salesforce\n• Nanodegree in Data Science — Imagecon India",
            "Santhosh holds certifications from Oracle (GenAI Professional), Salesforce (AI Associate), and Imagecon India (Data Science Nanodegree).",
            "Certified in GenAI (Oracle), AI Associate (Salesforce), and Data Science (Imagecon India) — validating his expertise across the AI/ML landscape! 📜"
        ]
    },
    'contact': {
        'triggers': [
            'contact', 'reach', 'email', 'phone', 'get in touch',
            'hire', 'connect', 'how to contact', 'reach out',
            'message him', 'talk to santhosh'
        ],
        'responses': [
            "📬 Reach Santhosh at:\n• Email: bvmsanthosh@gmail.com\n• LinkedIn: linkedin.com/in/santhoshmohankumar-6751a6232\n• GitHub: github.com/MSanthosh3\n\nOr use the contact form below! 👇",
            "You can connect with Santhosh via email (bvmsanthosh@gmail.com), LinkedIn, or GitHub. Or just scroll down and fill out the contact form!",
            "Best ways to reach Santhosh: email bvmsanthosh@gmail.com, or connect on LinkedIn/GitHub. The contact form below works too! 📬"
        ]
    },
    'hobbies': {
        'triggers': [
            'hobbies', 'free time', 'fun', 'interests',
            'what do you do for fun', 'outside work', 'sports',
            'games', 'playstation', 'cricket hobby', 'football hobby'
        ],
        'responses': [
            "When not building AI systems, Santhosh enjoys 🏏 Cricket, ⚽ Football, 🏸 Badminton, and 🎮 PS gaming (especially FC 26)! A sports enthusiast and gamer at heart.",
            "Outside of AI/ML, Santhosh is into cricket, football, badminton, and PlayStation gaming (FC 26 is a current fave). Sports + gaming keep the mind sharp! 🎮",
            "Hobbies? Cricket, football, badminton, and PS gaming (FC 26)! Santhosh balances code with sports and gaming. 🏏⚽🎮"
        ]
    },
    'availability': {
        'triggers': [
            'available', 'freelance', 'open to work', 'hiring',
            'looking for work', 'collaborate', 'opportunity', 'job opening'
        ],
        'responses': [
            "Santhosh is always open to exciting AI/ML opportunities and collaborations! Reach out via bvmsanthosh@gmail.com or the contact form below. 🚀",
            "Interested in collaborating or have an opportunity? Santhosh is open to AI/ML roles and projects. Drop a message via the contact form or email him!",
            "Yes! Santhosh is open to new opportunities in AI/ML engineering. Connect via email (bvmsanthosh@gmail.com) or the contact form. Let's build something great! 🚀"
        ]
    },
    'laravel': {
        'triggers': [
            'laravel', 'php', 'react', 'web development', 'database migration', 'db migration', 'migration'
        ],
        'responses': [
            "Santhosh worked in PHP, Laravel, and React for some time, and his standout task was DB migration.",
            "Yes, he has experience working in PHP, Laravel, and React. His standout task was database migration!",
            "Santhosh worked with PHP, Laravel, and React for some time, with DB migration being his standout task. 🚀"
        ]
    },
    'location': {
        'triggers': [
            'where are you from', 'location', 'where do you live',
            'based in', 'city', 'country', 'salem', 'tamil nadu', 'india'
        ],
        'responses': [
            "📍 Santhosh is based in Salem, Tamil Nadu, India.",
            "He's located in Salem, Tamil Nadu, India 🇮🇳",
            "Based in Salem, Tamil Nadu, India — the heart of South India! 📍"
        ]
    },
    'thanks': {
        'triggers': [
            'thank you', 'thanks', 'appreciate', 'helpful',
            'great', 'awesome', 'nice', 'cool', 'good job'
        ],
        'responses': [
            "You're welcome! 😊 Feel free to ask anything else about Santhosh's work!",
            "Glad I could help! Anything else you'd like to know? 🙌",
            "Thanks for your kind words! Don't hesitate to ask more questions. 😄"
        ]
    },
    'goodbye': {
        'triggers': [
            'bye', 'goodbye', 'see you', 'take care', 'later',
            'gotta go', 'cya', 'peace out'
        ],
        'responses': [
            "Goodbye! 👋 Thanks for visiting Santhosh's portfolio. Have a great day!",
            "See you later! Feel free to come back anytime. 🚀",
            "Take care! Don't forget to check out the projects section before you go. 👋"
        ]
    }
}

FALLBACK_RESPONSES = [
    "Hmm, I'm not sure about that one! 🤔 I'm best at answering questions about Santhosh's skills, projects, experience, or education. Try asking about those!",
    "That's a bit outside my expertise! I'm here to talk about Santhosh M's work in AI/ML. Ask me about his projects, tech stack, or career!",
    "Interesting question, but I'm specifically tuned to discuss Santhosh's portfolio! 😄 Try asking about his skills, projects, or experience.",
    "I wish I could help with that! For now, I'm focused on Santhosh's professional background. Try: 'What are your skills?' or 'Tell me about CricBot'!"
]


def normalize_text(text):
    """Normalize user input for matching."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)  # Remove punctuation
    text = re.sub(r'\s+', ' ', text)     # Collapse whitespace
    return text


def get_chatbot_response(user_message):
    """Match user message against knowledge base using fuzzy matching."""
    normalized = normalize_text(user_message)

    if not normalized:
        return random.choice(FALLBACK_RESPONSES)

    best_score = 0
    best_topic = None

    for topic, data in KNOWLEDGE_BASE.items():
        for trigger in data['triggers']:
            score = fuzz.token_set_ratio(normalized, trigger)
            if score > best_score:
                best_score = score
                best_topic = topic

    if best_score >= CONFIDENCE_THRESHOLD and best_topic:
        return random.choice(KNOWLEDGE_BASE[best_topic]['responses'])

    return random.choice(FALLBACK_RESPONSES)


# ─── Routes ─────────────────────────────────────────────────────

@app.route('/')
def index():
    """Serve portfolio page and log visitor."""
    try:
        conn = get_db()
        conn.execute(
            'INSERT INTO visitors (ip_address, user_agent, timestamp) VALUES (?, ?, ?)',
            (get_real_ip(), request.user_agent.string, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Don't break the page if DB logging fails
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chatbot messages."""
    data = request.get_json(silent=True)
    if not data or 'message' not in data:
        return jsonify({'error': 'No message provided'}), 400

    message = str(data['message']).strip()
    if not message:
        return jsonify({'error': 'Empty message'}), 400
    if len(message) > MAX_MESSAGE_LENGTH:
        return jsonify({'error': f'Message too long (max {MAX_MESSAGE_LENGTH} chars)'}), 400

    response = get_chatbot_response(message)
    return jsonify({'response': response})


@app.route('/api/contact', methods=['POST'])
def contact():
    """Handle contact form submissions."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    name = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip()
    message = str(data.get('message', '')).strip()

    # Validation
    if not name or not email or not message:
        return jsonify({'error': 'All fields are required'}), 400
    if len(name) > 100:
        return jsonify({'error': 'Name is too long'}), 400
    if len(email) > 200 or '@' not in email:
        return jsonify({'error': 'Invalid email address'}), 400
    if len(message) > 2000:
        return jsonify({'error': 'Message is too long (max 2000 chars)'}), 400

    try:
        conn = get_db()
        conn.execute(
            'INSERT INTO messages (name, email, message, timestamp) VALUES (?, ?, ?, ?)',
            (name, email, message, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Message sent successfully!'})
    except Exception as e:
        return jsonify({'error': 'Failed to save message. Please try again.'}), 500


@app.route('/resume')
def download_resume():
    """Serve the resume PDF as a download."""
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    resume_file = 'Santhosh_M_Resume.pdf'
    resume_path = os.path.join(static_dir, resume_file)
    if not os.path.exists(resume_path):
        return jsonify({'error': 'Resume not found. Please place Santhosh_M_Resume.pdf in the static/ folder.'}), 404
    return send_from_directory(static_dir, resume_file, as_attachment=True,
                               download_name='Santhosh_M_Resume.pdf')


@app.route('/dashboard/login', methods=['GET', 'POST'])
def dashboard_login():
    """Dashboard login page."""
    if session.get('authenticated'):
        return redirect(url_for('dashboard'))

    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('dashboard'))
        else:
            error = 'Incorrect password. Please try again.'

    return render_template('dashboard.html', show_login=True, error=error)


@app.route('/dashboard')
def dashboard():
    """Analytics dashboard — protected by session auth."""
    if not session.get('authenticated'):
        return redirect(url_for('dashboard_login'))

    conn = get_db()
    visitors_raw = conn.execute(
        'SELECT * FROM visitors ORDER BY timestamp DESC'
    ).fetchall()
    messages_list = conn.execute(
        'SELECT * FROM messages ORDER BY timestamp DESC'
    ).fetchall()
    conn.close()

    # Parse user agents for display
    visitors = []
    for v in visitors_raw:
        visitors.append({
            'id': v['id'],
            'ip_address': v['ip_address'],
            'device': parse_user_agent(v['user_agent']),
            'timestamp': v['timestamp']
        })

    return render_template(
        'dashboard.html',
        show_login=False,
        visitors=visitors,
        messages=messages_list,
        visitor_count=len(visitors),
        message_count=len(messages_list)
    )


@app.route('/dashboard/logout')
def dashboard_logout():
    """Clear session and redirect."""
    session.pop('authenticated', None)
    return redirect(url_for('index'))


# ─── App Startup ────────────────────────────────────────────────

init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
