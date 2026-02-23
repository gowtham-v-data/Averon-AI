from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
from pypdf import PdfReader
import requests
import os
import uuid
import io
from gtts import gTTS
from fastapi.responses import StreamingResponse
import json
import re

def clean_json_response(text: str) -> str:
    """Clean LLM response to extract valid JSON, stripping markdown fences and extra text."""
    text = text.strip()
    
    # Remove markdown code fences: ```json ... ``` or ``` ... ```
    # Handle both ```json and ```JSON and just ```
    text = re.sub(r'^```(?:json|JSON)?\s*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text)
    text = text.strip()
    
    # If there's still extra text before/after the JSON, try to extract just the JSON object
    # Find the first { and last }
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]
    
    return text

# Load environment variables
load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Validate required environment variables
if not GROQ_API_KEY:
    print("⚠️ WARNING: GROQ_API_KEY not found in environment variables!")
    print("   Please add it to your .env file")

if not PINECONE_API_KEY:
    print("⚠️ WARNING: PINECONE_API_KEY not found in environment variables!")
    
if not INDEX_NAME:
    print("⚠️ WARNING: PINECONE_INDEX_NAME not found in environment variables!")

print("✅ Environment variables loaded")
print(f"   GROQ_API_KEY: {'✓ Set' if GROQ_API_KEY else '✗ Missing'}")
print(f"   PINECONE_API_KEY: {'✓ Set' if PINECONE_API_KEY else '✗ Missing'}")
print(f"   INDEX_NAME: {INDEX_NAME if INDEX_NAME else '✗ Missing'}")

# Initialize app
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
# Database connection can take time, we wrap it in a try-except
DATABASE_URL = "postgresql://postgres:gow%402005@localhost/claude_clone"
try:
    engine = create_engine(DATABASE_URL)
except Exception as e:
    print(f"Warning: Database connection failed: {e}")

# Initialize embedding model (Small and fast)
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# Initialize Pinecone
try:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(INDEX_NAME)
except Exception as e:
    print(f"Warning: Pinecone initialization failed: {e}")


class ChatRequest(BaseModel):
    message: str

class TTSRequest(BaseModel):
    text: str

# Keywords that indicate the user is asking about uploaded documents
DOC_KEYWORDS = ["pdf", "document", "file", "upload", "summarize", "summary", "resume", "attached", "knowledge base"]

# Keywords for website builder detection (includes common typos)
BUILD_KEYWORDS = ["build", "bulid", "biuld", "buid", "create", "make", "generate", "design", "develop"]
SITE_KEYWORDS = ["website", "webpage", "web page", "web site", "site", "landing page", "web app", "webapp", "homepage", "home page"]

def is_builder_request(msg: str) -> bool:
    """Check if the user wants to build a website (flexible matching with typo tolerance)."""
    msg_lower = msg.lower()
    has_build = any(kw in msg_lower for kw in BUILD_KEYWORDS)
    has_site = any(kw in msg_lower for kw in SITE_KEYWORDS)
    return has_build and has_site

# ─── WEBSITE BUILDER: SYSTEM MESSAGE ─────────────────────────────────────────
BUILDER_SYSTEM_MSG = (
    "You are an elite frontend architect at a world-class design agency "
    "(think Vercel, Linear, Stripe quality). "
    "You generate complete, production-ready website code that could be deployed immediately. "
    "You respond ONLY with valid JSON containing a 'files' array. "
    "Each file object has 'name' (string) and 'content' (string) keys. "
    "You NEVER include markdown formatting, explanations, backticks, or commentary — ONLY the raw JSON object. "
    "Your websites are visually stunning with premium aesthetics, fully responsive, accessible, "
    "and feature smooth modern animations. "
    "Every page you build looks like it was crafted by a senior developer with 10+ years of experience."
)

# ─── WEBSITE BUILDER: PROMPT GENERATOR ────────────────────────────────────────
def get_builder_prompt(user_message: str) -> str:
    """Generate the professional builder prompt for the LLM."""
    return (
        f"PROJECT BRIEF: {user_message}\n"
        "\n"
        "OUTPUT: Return ONLY a valid JSON object with this structure:\n"
        '{"files": [{"name": "index.html", "content": "..."}, {"name": "about.html", "content": "..."}, '
        '{"name": "services.html", "content": "..."}, {"name": "contact.html", "content": "..."}, '
        '{"name": "style.css", "content": "..."}, {"name": "script.js", "content": "..."}]}\n'
        "\n"
        "━━━━━━━ HTML ARCHITECTURE ━━━━━━━\n"
        '• DOCTYPE html with lang="en"\n'
        "• <head>: charset UTF-8, viewport meta, unique <title>, meta description, Open Graph tags, link to style.css\n"
        '• Google Fonts: Import "Inter" font (weights 300,400,500,600,700) via <link> tag — use as primary font-family\n'
        "• Semantic HTML5: <header>, <nav>, <main>, <section>, <article>, <footer>\n"
        "• Every page shares the SAME <header> with logo + responsive navigation + mobile hamburger icon\n"
        "• Every page shares the SAME <footer> with organized link columns, social icons (Unicode/SVG), copyright with auto-year\n"
        "• Navigation highlights the current active page with a CSS class\n"
        '• All internal links work correctly (href="about.html" etc.)\n'
        "• Add smooth scroll: html { scroll-behavior: smooth }\n"
        "• script.js loaded with defer attribute\n"
        "\n"
        "━━━━━━━ PAGE DETAILS ━━━━━━━\n"
        "\n"
        "INDEX.HTML — Home Page:\n"
        "• Hero section: large bold heading, compelling subtitle, gradient or overlay background, 1-2 CTA buttons with hover effects\n"
        "• Features/services grid: 3-4 cards with Unicode icons, title, description\n"
        "• Social proof section: testimonials carousel OR animated stats/counters\n"
        "• Call-to-action banner with gradient background before footer\n"
        "\n"
        "ABOUT.HTML — About Page:\n"
        "• Hero banner with page title and breadcrumb\n"
        "• Brand story section with side-by-side layout (text + visual placeholder)\n"
        "• Mission / Vision / Values in a 3-column grid with icons\n"
        "• Team section OR timeline/milestones section\n"
        "\n"
        "SERVICES.HTML — Services/Products Page:\n"
        "• Hero banner with page title\n"
        "• Service/product cards in responsive grid (icon, title, description, price/CTA)\n"
        "• FAQ accordion section with working JavaScript expand/collapse and smooth height animation\n"
        "• Comparison table or pricing tiers if relevant\n"
        "\n"
        "CONTACT.HTML — Contact Page:\n"
        "• Hero banner with page title\n"
        "• Contact form: name, email, phone, subject <select>, message <textarea>, submit button\n"
        "• Full form validation with JavaScript + visual error/success states\n"
        "• Contact info cards with icons\n"
        "• Business hours or additional info section\n"
        "\n"
        "━━━━━━━ CSS DESIGN SYSTEM ━━━━━━━\n"
        "• CSS Custom Properties (--variables) for: colors (primary, secondary, accent, bg, text, border), spacing scale, border-radius, shadows, font-sizes\n"
        "• Professional color palette: dark rich backgrounds (#0a0a0a, #111827, #1e293b) with vibrant accents — OR a light clean theme with bold accent colors. Follow the 60-30-10 color rule.\n"
        "• Typography: font-family 'Inter', sans-serif. Use clamp() for fluid responsive font sizes. Proper hierarchy (h1 > h2 > h3 > body).\n"
        "• Layered box-shadows for depth: --shadow-sm, --shadow-md, --shadow-lg, --shadow-xl\n"
        "• Gradient backgrounds on hero sections using linear-gradient or radial-gradient with beautiful color stops\n"
        "• Glassmorphism where appropriate: backdrop-filter: blur(12px); background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1)\n"
        "• Smooth transitions on ALL interactive elements: transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1)\n"
        "• Button styles: primary (filled gradient), secondary (outlined), ghost — all with hover scale + shadow elevation + color shift\n"
        "• Card hover effect: transform: translateY(-4px) with enhanced shadow\n"
        "• Sticky header with backdrop-filter blur, gains shadow on scroll via JS class .scrolled\n"
        "• Mobile hamburger menu: smooth slide-in or dropdown animation\n"
        "• Responsive: mobile-first, breakpoints at 768px and 1024px using @media\n"
        "• @keyframes for: fadeInUp, fadeInLeft, fadeInRight, scaleIn — used with .visible class\n"
        "• Form inputs: custom styled with focus ring (box-shadow outline), error state (red border), success state (green border)\n"
        "• Footer: darker background, multi-column grid layout\n"
        "• Smooth scrollbar styling (webkit-scrollbar)\n"
        "• Selection color styling (::selection)\n"
        "\n"
        "━━━━━━━ JAVASCRIPT FEATURES ━━━━━━━\n"
        "• DOMContentLoaded wrapper for all code\n"
        "• Mobile menu: hamburger toggle with classList.toggle, animate open/close\n"
        "• Sticky header: window scroll listener — add .scrolled class when scrollY > 50\n"
        '• Smooth scroll for all anchor links (querySelectorAll(\'a[href^="#"]\'))\n'
        "• Active nav highlighting: compare window.location with href, add .active class\n"
        "• Scroll-reveal animations: IntersectionObserver on elements with [data-animate] — add .visible class\n"
        "• FAQ accordion: querySelectorAll('.faq-item'), click toggles .active, smooth max-height transition\n"
        "• Contact form: addEventListener('submit'), validate all fields, display inline error messages, show success message on valid submit (preventDefault)\n"
        "• Stats counter: IntersectionObserver triggers countUp animation (setInterval from 0 to target)\n"
        "• Back-to-top button: appears when scrollY > 300, smooth scroll to top on click\n"
        "• Auto-update copyright year: textContent = new Date().getFullYear()\n"
        "• NO external libraries — 100% vanilla JavaScript\n"
        "• Clean modular code with descriptive function names and comments\n"
        "\n"
        "━━━━━━━ QUALITY STANDARDS ━━━━━━━\n"
        "• ZERO placeholder text — all content realistic and contextual to the project brief\n"
        "• ZERO broken links — every href points to a valid page\n"
        "• Accessibility: alt on images, ARIA labels on buttons/nav, :focus-visible outlines, prefers-reduced-motion media query\n"
        "• SEO: unique <title> and <meta description> per page, single <h1> per page, proper heading hierarchy\n"
        "• Clean indented code with meaningful BEM-inspired class names (e.g., .hero__title, .card--featured)\n"
        "• Production-ready — deployable as-is to any static hosting\n"
        "• Output ONLY the JSON object — no markdown, no explanations, no backticks"
    )


@app.post("/chat")
def chat(req: ChatRequest):
    user_message = req.message.strip()
    
    # Check if API key is configured
    if not GROQ_API_KEY:
        return {"reply": "⚠️ Server configuration error: GROQ API key is missing. Please contact the administrator."}

    # WEBSITE BUILDER MODE
    if is_builder_request(user_message):
        builder_prompt = get_builder_prompt(user_message)
        print(f"🔨 Website builder triggered for: {user_message[:80]}...")

        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": BUILDER_SYSTEM_MSG},
                        {"role": "user", "content": builder_prompt}
                    ],
                    "temperature": 0.4,
                    "max_tokens": 8192,
                    "response_format": {"type": "json_object"}
                },
                timeout=120
            )
            result = response.json()
            
            print(f"Website builder API response status: {response.status_code}")
            
            if "error" in result:
                error_msg = result["error"].get("message", "Unknown error")
                print(f"Website builder API error: {error_msg}")
                return {"reply": f"Error generating website: {error_msg}"}
            
            if "choices" not in result:
                print(f"Unexpected website builder response: {result}")
                return {"reply": "Error generating website. Please try again."}
            
            raw_content = result["choices"][0]["message"]["content"]
            print(f"Website builder raw response length: {len(raw_content)} chars")
            
            # Clean up the response: strip markdown code fences and extra text
            cleaned = clean_json_response(raw_content)
            
            # Validate it's actually parseable JSON
            try:
                parsed = json.loads(cleaned)
                
                # Handle case where files might be nested differently
                if "files" not in parsed:
                    # Try to find files key in any nested structure
                    print(f"JSON keys received: {list(parsed.keys())}")
                    return {"reply": "Error: AI generated invalid website structure. Please try again with a simpler request."}
                
                # Validate each file has name and content
                for f in parsed["files"]:
                    if "name" not in f or "content" not in f:
                        print(f"Invalid file structure: {list(f.keys())}")
                        return {"reply": "Error: AI generated incomplete files. Please try again."}
                
                print(f"✅ Website built successfully! {len(parsed['files'])} files generated.")
                for f in parsed["files"]:
                    print(f"   📄 {f['name']} ({len(f['content'])} chars)")
                
                # Return the cleaned, validated JSON string
                return {"builder": json.dumps(parsed)}
                
            except json.JSONDecodeError as je:
                print(f"JSON parse error after cleanup: {je}")
                print(f"Raw content (first 500 chars): {raw_content[:500]}")
                return {"reply": "Error: AI response was not valid JSON. Please try again."}
            
        except requests.exceptions.Timeout:
            print("Website builder request timed out")
            return {"reply": "Website generation timed out. Please try a simpler request."}
        except Exception as e:
            print(f"Website builder error: {e}")
            return {"reply": f"Error generating website: {str(e)}"}

    # NORMAL RAG CHAT MODE
    # 1. History
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT role, content FROM messages ORDER BY created_at DESC LIMIT 10"))
            history = [{"role": row[0], "content": row[1]} for row in res]
            history.reverse()
    except Exception as e:
        print(f"⚠️ History fetch error: {e}")
        history = []

    # 2. Check if user is asking about uploaded documents
    is_doc_query = any(kw in user_message.lower() for kw in DOC_KEYWORDS)
    
    # 3. Get list of uploaded files for context
    uploaded_filenames = []
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT filename FROM uploaded_files ORDER BY uploaded_at DESC"))
            uploaded_filenames = [row[0] for row in res]
    except Exception as e:
        print(f"⚠️ File list fetch error: {e}")

    # 4. Vector Search - use more results for document queries
    context = ""
    try:
        query_embedding = embedding_model.encode(user_message).tolist()
        # Fetch more chunks when user asks about documents
        top_k = 15 if is_doc_query else 5
        results = index.query(vector=query_embedding, top_k=top_k, include_metadata=True)
        
        if results["matches"]:
            context = "\n".join([m["metadata"]["text"] for m in results["matches"]])
            print(f"✅ Vector search returned {len(results['matches'])} results (top_k={top_k})")
            print(f"   Context preview: {context[:200]}...")
        else:
            print("⚠️ Vector search returned 0 matches")
            context = ""
    except Exception as e:
        print(f"❌ Vector search error: {e}")
        context = ""

    # 5. Build system prompt with knowledge base awareness
    system_prompt = "You are Averon, a powerful and helpful AI assistant. You are friendly, knowledgeable, and provide clear, well-structured responses."
    if uploaded_filenames:
        file_list = ", ".join(uploaded_filenames)
        system_prompt += f"\n\nThe user has uploaded the following documents to the knowledge base: {file_list}."
        system_prompt += "\nYou have access to the content of these documents through the context provided below."
        system_prompt += "\nWhen the user asks about their uploaded documents, PDFs, or files, use the provided context to answer."
        system_prompt += "\nIf the user asks to summarize a document, provide a thorough summary based on the context."

    # 6. LLM Call
    messages = [
        {"role": "system", "content": system_prompt},
    ]
    
    # Only add context if we actually have some
    if context.strip():
        messages.append({"role": "system", "content": f"Content from the user's uploaded documents:\n{context}"})
    
    messages += history
    messages.append({"role": "user", "content": user_message})

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={"model": "llama-3.1-8b-instant", "messages": messages},
            timeout=30
        )
        result = response.json()
        
        # Check if API returned an error
        if "error" in result:
            error_msg = result["error"].get("message", "Unknown API error")
            print(f"API Error: {error_msg}")
            return {"reply": f"Sorry, I encountered an error: {error_msg}"}
        
        # Check if response has expected format
        if "choices" not in result:
            print(f"Unexpected API response: {result}")
            return {"reply": "Sorry, I received an unexpected response from the AI service. Please try again."}
        
        reply = result["choices"][0]["message"]["content"]
        
    except requests.exceptions.Timeout:
        print("API request timed out")
        return {"reply": "Sorry, the request timed out. Please try again."}
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return {"reply": "Sorry, I'm having trouble connecting to the AI service. Please try again later."}
    except Exception as e:
        print(f"Unexpected error: {e}")
        return {"reply": "Sorry, an unexpected error occurred. Please try again."}

    # 7. Save
    try:
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO messages (role, content) VALUES (:r, :c)"), {"r": "user", "c": user_message})
            conn.execute(text("INSERT INTO messages (role, content) VALUES (:r, :c)"), {"r": "assistant", "c": reply})
            conn.commit()
    except Exception as e:
        print(f"⚠️ Message save error: {e}")

    return {"reply": reply}

@app.post("/tts")
async def text_to_speech(req: TTSRequest):
    """Generate speech audio from text using Google TTS"""
    try:
        # Create TTS object
        tts = gTTS(text=req.text, lang='en', slow=False)
        
        # Save to BytesIO buffer
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        
        # Return as streaming audio response
        return StreamingResponse(
            audio_buffer,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=speech.mp3"
            }
        )
    except Exception as e:
        print(f"TTS Error: {e}")
        return {"error": str(e)}

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    filename = file.filename.lower()
    original_filename = file.filename  # Keep original name for display
    file_text = ""

    print(f"📄 Upload request received: {filename}")

    try:
        file_bytes = await file.read()

        if filename.endswith(".pdf"):
            reader = PdfReader(io.BytesIO(file_bytes))
            file_text = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])
            print(f"   PDF pages: {len(reader.pages)}, extracted text length: {len(file_text)} chars")

        elif filename.endswith(".csv"):
            import pandas as pd
            df = pd.read_csv(io.BytesIO(file_bytes))
            file_text = df.to_string()
            print(f"   CSV rows: {len(df)}, columns: {list(df.columns)}")

        elif filename.endswith((".xlsx", ".xls")):
            import pandas as pd
            df = pd.read_excel(io.BytesIO(file_bytes))
            file_text = df.to_string()
            print(f"   Excel rows: {len(df)}, columns: {list(df.columns)}")

        elif filename.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(file_bytes))
            file_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            print(f"   DOCX paragraphs: {len(doc.paragraphs)}")

        elif filename.endswith(".doc"):
            # .doc files need different handling - try to read as text
            try:
                file_text = file_bytes.decode('utf-8', errors='ignore')
            except:
                file_text = file_bytes.decode('latin-1', errors='ignore')
            print(f"   DOC text length: {len(file_text)} chars")

        elif filename.endswith(".txt"):
            file_text = file_bytes.decode('utf-8', errors='ignore')
            print(f"   TXT text length: {len(file_text)} chars")

        elif filename.endswith(".json"):
            file_text = file_bytes.decode('utf-8', errors='ignore')
            print(f"   JSON text length: {len(file_text)} chars")

        else:
            # Try to read as plain text for any other file
            try:
                file_text = file_bytes.decode('utf-8', errors='ignore')
                print(f"   Generic file read as text: {len(file_text)} chars")
            except:
                return {"error": f"Unsupported file type: {filename.split('.')[-1]}"}

    except Exception as e:
        print(f"   ❌ File read error: {e}")
        return {"error": f"Error reading file: {str(e)}"}

    if not file_text.strip():
        print(f"   ⚠️ No text extracted from {filename}")
        return {"error": "Empty file or no text could be extracted."}

    print(f"   📝 Text preview: {file_text[:200]}...")

    # Vectorize
    chunks = [file_text[i:i+500] for i in range(0, len(file_text), 500)]
    vectors = []
    for chunk in chunks:
        vectors.append({
            "id": str(uuid.uuid4()),
            "values": embedding_model.encode(chunk).tolist(),
            "metadata": {"text": chunk, "filename": filename}
        })
    index.upsert(vectors)
    print(f"   ✅ Upserted {len(vectors)} chunks to Pinecone")

    # Database Log
    try:
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO uploaded_files (filename) VALUES (:f)"), {"f": original_filename})
            conn.commit()
        print(f"   ✅ Logged {original_filename} to database")
    except Exception as e:
        print(f"   ⚠️ DB log error: {e}")

    return {"status": f"{original_filename} uploaded successfully!"}

@app.get("/files")
def get_files():
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT id, filename, uploaded_at FROM uploaded_files ORDER BY uploaded_at DESC"))
            return {"files": [{"id": r[0], "filename": r[1], "uploaded_at": str(r[2])} for r in res]}
    except:
        return {"files": []}

@app.get("/tts")
def text_to_speech_get(text_input: str):
    print(f"TTS Request: {text_input[:50]}...")
    if not text_input.strip():
        return {"error": "No text provided"}
    try:
        tts = gTTS(text=text_input, lang='en')
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        return StreamingResponse(audio_fp, media_type="audio/mpeg")
    except Exception as e:
        print(f"TTS Error: {e}")
        return {"error": str(e)}

@app.post("/clear-chat")
def clear_chat():
    """Clear all chat messages from the database for a fresh conversation."""
    try:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM messages"))
            conn.commit()
        print("🧹 Chat history cleared")
        return {"status": "Chat history cleared."}
    except Exception as e:
        print(f"⚠️ Clear chat error: {e}")
        return {"error": str(e)}

@app.post("/clear-docs")
def clear_documents():
    try:
        index.delete(delete_all=True)
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM uploaded_files"))
            conn.commit()
        return {"status": "Cleared."}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)