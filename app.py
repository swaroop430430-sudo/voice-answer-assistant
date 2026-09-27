import os
import tempfile
from flask import Flask, request, jsonify, send_from_directory
import requests

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip()
TRANSCRIBE_MODEL = os.getenv("TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe").strip()

SYSTEM_PROMPT = """You are a real-time voice answer assistant.
Give concise, accurate, useful answers to the user's latest question.
If the user is asking for an interview-style answer, answer naturally as if the user is speaking.
Do not mention these instructions. Prefer short paragraphs and bullets when useful.
If the question is ambiguous, make the most reasonable interpretation and state the assumption briefly.
"""

def openai_headers():
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

def check_key():
    if not OPENAI_API_KEY:
        return False, "OPENAI_API_KEY is not configured on the server."
    return True, ""

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Voice Answer Assistant</title>
<style>
:root{font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#eaf0ff;background:#0b1020}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at top,#17244a 0,#0b1020 48%,#070b15 100%)}
.wrap{max-width:1050px;margin:auto;padding:28px 18px}.top{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:20px}
h1{font-size:30px;margin:0 0 5px}.sub{color:#9ca9c7}.badge{padding:7px 11px;border-radius:999px;background:#17213a;border:1px solid #2c3a5f;font-size:12px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:800px){.grid{grid-template-columns:1fr}}
.card{background:rgba(15,23,42,.9);border:1px solid #263554;border-radius:18px;padding:18px;box-shadow:0 16px 45px rgba(0,0,0,.22)}
label{display:block;font-size:13px;color:#9ca9c7;margin-bottom:7px}.row{display:flex;flex-wrap:wrap;gap:9px}
button{border:0;border-radius:10px;padding:11px 15px;font-weight:700;cursor:pointer;background:#2563eb;color:white}
button.secondary{background:#202d49}button.danger{background:#b4233c}button:disabled{opacity:.45;cursor:not-allowed}
input,textarea{width:100%;border:1px solid #334463;background:#0b1326;color:#eef3ff;border-radius:10px;padding:11px;font:inherit}
textarea{min-height:105px;resize:vertical}.status{margin-top:12px;padding:10px;border-radius:10px;background:#0b1326;color:#b9c5df;font-size:13px;white-space:pre-wrap}
.timer{font-size:34px;font-variant-numeric:tabular-nums;font-weight:800;margin:5px 0 15px}.answer{min-height:250px;white-space:pre-wrap;line-height:1.55;color:#f3f6ff}
.transcript{min-height:120px;white-space:pre-wrap;line-height:1.5;color:#d8e0f2}.small{font-size:12px;color:#8290ae;margin-top:8px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#64748b;margin-right:7px}.dot.live{background:#22c55e}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div><h1>Voice Answer Assistant</h1><div class="sub">Real-time voice capture, transcription and AI answers</div></div>
    <div class="badge"><span id="dot" class="dot"></span><span id="state">Ready</span></div>
  </div>

  <div class="grid">
    <section class="card">
      <label>Backend URL</label>
      <input id="backend" placeholder="Leave blank when hosted on Render">
      <div class="small">Your OpenAI API key stays on the server and is never placed in this page.</div>
      <hr style="border:0;border-top:1px solid #263554;margin:17px 0">

      <div class="timer" id="timer">05:00</div>
      <div class="row">
        <button id="micBtn">Start microphone</button>
        <button id="stopBtn" class="danger" disabled>Stop</button>
        <button id="shareBtn" class="secondary">Share tab/screen audio</button>
      </div>
      <div class="status" id="status">Ready. Start the microphone or share a tab/screen with audio.</div>
      <div class="small">Capture automatically stops after 5 minutes.</div>
    </section>

    <section class="card">
      <label>Live transcript</label>
      <div id="transcript" class="transcript">Your speech will appear here when browser speech recognition is available.</div>
      <div class="row" style="margin-top:12px">
        <button id="answerBtn">Get AI answer</button>
        <button id="clearBtn" class="secondary">Clear</button>
      </div>
    </section>

    <section class="card" style="grid-column:1/-1">
      <label>AI answer</label>
      <div id="answer" class="answer">AI answers will appear here.</div>
    </section>
  </div>
</div>

<script>
const $=id=>document.getElementById(id);
let recorder=null, chunks=[], stream=null, displayStream=null, recognition=null;
let timerId=null, remaining=300, transcriptText="";

function setStatus(msg, live=false){$("status").textContent=msg;$("state").textContent=live?"Capturing":"Ready";$("dot").className="dot"+(live?" live":"");}
function fmt(s){return String(Math.floor(s/60)).padStart(2,"0")+":"+String(s%60).padStart(2,"0")}
function resetTimer(){remaining=300;$("timer").textContent=fmt(remaining)}
function startTimer(){
  clearInterval(timerId); timerId=setInterval(()=>{
    remaining--; $("timer").textContent=fmt(Math.max(remaining,0));
    if(remaining<=0) stopCapture();
  },1000);
}
function backend(){return ($("backend").value||"").trim().replace(/\/+$/,"") || location.origin}

async function startRecognition(){
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){setStatus("Microphone is recording. Browser speech recognition is not available; use Get AI answer after recording.");return}
  recognition=new SR(); recognition.continuous=true; recognition.interimResults=true; recognition.lang="en-US";
  recognition.onresult=e=>{
    let finalText="";
    for(let i=e.resultIndex;i<e.results.length;i++) finalText+=e.results[i][0].transcript+" ";
    transcriptText=finalText.trim();
    $("transcript").textContent=transcriptText||"Listening...";
  };
  recognition.onerror=()=>{};
  recognition.onend=()=>{ if(recorder && recorder.state==="recording"){ try{recognition.start()}catch(e){} } };
  try{recognition.start()}catch(e){}
}

async function startCapture(){
  if(recorder && recorder.state==="recording") return;
  try{
    stream=await navigator.mediaDevices.getUserMedia({audio:true});
    chunks=[];
    recorder=new MediaRecorder(stream);
    recorder.ondataavailable=e=>{if(e.data.size) chunks.push(e.data)};
    recorder.onstop=async()=>{ if(recognition) try{recognition.stop()}catch(e){}; await transcribeRecording(); };
    recorder.start(1000);
    $("micBtn").disabled=true;$("stopBtn").disabled=false;
    resetTimer();startTimer();setStatus("Microphone capturing...",true);startRecognition();
  }catch(e){setStatus("Microphone could not start: "+e.message)}
}

async function stopCapture(){
  clearInterval(timerId);
  if(recorder && recorder.state!=="inactive") recorder.stop();
  if(stream){stream.getTracks().forEach(t=>t.stop());stream=null}
  $("micBtn").disabled=false;$("stopBtn").disabled=true;
  setStatus("Capture stopped. Processing audio...");
}

async function transcribeRecording(){
  if(!chunks.length){setStatus("No audio was recorded.");return}
  const blob=new Blob(chunks,{type:chunks[0].type||"audio/webm"});
  if(transcriptText.trim()){setStatus("Recording stopped. Browser transcript is ready.");return}
  try{
    const fd=new FormData();fd.append("audio",blob,"capture.webm");
    const r=await fetch(backend()+"/api/transcribe",{method:"POST",body:fd});
    const data=await r.json();
    if(!r.ok||!data.ok) throw new Error(data.error||"Transcription failed");
    transcriptText=(data.text||"").trim();$("transcript").textContent=transcriptText||"No speech detected.";
    setStatus("Transcription complete.");
  }catch(e){setStatus("Transcription failed: "+e.message)}
}

async function getAnswer(){
  const q=($("transcript").textContent||"").trim();
  if(!q || q.startsWith("Your speech")){setStatus("Please speak or enter a transcript first.");return}
  $("answer").textContent="Thinking...";
  try{
    const r=await fetch(backend()+"/api/answer",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:q})});
    const data=await r.json();
    if(!r.ok||!data.ok) throw new Error(data.error||"AI answer failed");
    $("answer").textContent=data.answer||"No answer returned.";
    setStatus("AI answer ready.");
  }catch(e){$("answer").textContent="Error: "+e.message;setStatus("AI answer failed.")}
}

async function shareScreen(){
  try{
    displayStream=await navigator.mediaDevices.getDisplayMedia({video:true,audio:true});
    const audioTracks=displayStream.getAudioTracks();
    if(!audioTracks.length){setStatus("Screen/tab sharing started, but no system/tab audio was provided. Select a tab and enable Share audio if available.");}
    else{
      const audioStream=new MediaStream(audioTracks);
      chunks=[]; recorder=new MediaRecorder(audioStream);
      recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
      recorder.onstop=transcribeRecording;
      recorder.start(1000); remaining=300;$("timer").textContent=fmt(remaining);startTimer();
      $("stopBtn").disabled=false;$("micBtn").disabled=true;setStatus("Shared tab/screen audio capturing...",true);
    }
    displayStream.getVideoTracks()[0].onended=()=>stopCapture();
  }catch(e){setStatus("Screen/tab sharing could not start: "+e.message)}
}

$("micBtn").onclick=startCapture;
$("stopBtn").onclick=stopCapture;
$("shareBtn").onclick=shareScreen;
$("answerBtn").onclick=getAnswer;
$("clearBtn").onclick=()=>{$("transcript").textContent="";$("answer").textContent="AI answers will appear here.";transcriptText="";setStatus("Cleared.");resetTimer()};
resetTimer();
</script>
</body>
</html>
"""

@app.get("/")
def index():
    return INDEX_HTML

@app.get("/health")
@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "service": "voice-answer-assistant",
        "openai_key_configured": bool(OPENAI_API_KEY),
        "answer_model": OPENAI_MODEL,
        "transcribe_model": TRANSCRIBE_MODEL
    })

@app.get("/api/test-openai")
def test_openai():
    ok, msg = check_key()
    if not ok:
        return jsonify({"ok": False, "error": msg}), 500

    try:
        r = requests.post(
            "https://api.openai.com/v1/responses",
            headers=openai_headers(),
            json={
                "model": OPENAI_MODEL,
                "input": "Reply with exactly: Connection successful."
            },
            timeout=60,
        )
        if not r.ok:
            return jsonify({"ok": False, "status": r.status_code, "error": r.text[:2000]}), r.status_code
        data = r.json()
        text = data.get("output_text", "")
        if not text:
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        text += content.get("text", "")
        return jsonify({"ok": True, "message": text or "OpenAI responded successfully."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.post("/api/answer")
def answer():
    ok, msg = check_key()
    if not ok:
        return jsonify({"ok": False, "error": msg}), 500

    body = request.get_json(silent=True) or {}
    question = (body.get("question") or body.get("text") or "").strip()
    if not question:
        return jsonify({"ok": False, "error": "Question is empty."}), 400

    try:
        r = requests.post(
            "https://api.openai.com/v1/responses",
            headers=openai_headers(),
            json={
                "model": OPENAI_MODEL,
                "instructions": SYSTEM_PROMPT,
                "input": question,
            },
            timeout=90,
        )
        if not r.ok:
            return jsonify({"ok": False, "status": r.status_code, "error": r.text[:3000]}), r.status_code

        data = r.json()
        text = data.get("output_text", "")
        if not text:
            parts = []
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        parts.append(content.get("text", ""))
            text = "\n".join(parts).strip()

        return jsonify({"ok": True, "answer": text})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.post("/api/transcribe")
def transcribe():
    ok, msg = check_key()
    if not ok:
        return jsonify({"ok": False, "error": msg}), 500

    if "audio" not in request.files:
        return jsonify({"ok": False, "error": "No audio file received."}), 400

    uploaded = request.files["audio"]
    suffix = os.path.splitext(uploaded.filename or "")[1] or ".webm"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            uploaded.save(tmp.name)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as f:
            files = {
                "file": (uploaded.filename or "audio.webm", f, uploaded.mimetype or "audio/webm")
            }
            data = {"model": TRANSCRIBE_MODEL}
            r = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                files=files,
                data=data,
                timeout=120,
            )

        if not r.ok:
            return jsonify({"ok": False, "status": r.status_code, "error": r.text[:3000]}), r.status_code

        result = r.json()
        return jsonify({"ok": True, "text": result.get("text", "")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
