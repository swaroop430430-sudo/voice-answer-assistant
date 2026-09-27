import os, base64, requests
from flask import Flask, request, jsonify, Response
app=Flask(__name__)
GEMINI_API_KEY=os.getenv("GEMINI_API_KEY","").strip()
GEMINI_MODEL=os.getenv("GEMINI_MODEL","gemini-2.5-flash-lite").strip()

INDEX_HTML='<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n<title>Voice Answer Assistant</title>\n<style>\nbody{margin:0;background:#0b1020;color:#eef3ff;font-family:Arial,sans-serif}.wrap{max-width:1050px;margin:auto;padding:28px 18px}\nh1{margin:0 0 6px}.sub,.small{color:#9ca9c7}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:800px){.grid{grid-template-columns:1fr}}\n.card{background:#0f172a;border:1px solid #263554;border-radius:18px;padding:18px}label{display:block;color:#9ca9c7;margin-bottom:7px;font-size:13px}\ninput{width:100%;box-sizing:border-box;background:#0b1326;color:white;border:1px solid #334463;border-radius:10px;padding:11px}\nbutton{border:0;border-radius:10px;padding:11px 15px;font-weight:bold;background:#2563eb;color:white;cursor:pointer;margin:3px}\nbutton.secondary{background:#26344f}button.danger{background:#b4233c}button:disabled{opacity:.45}\n.timer{font-size:34px;font-weight:bold;margin:15px 0}.status{margin-top:12px;padding:10px;background:#0b1326;border-radius:10px;color:#c8d2e8}\n.transcript,.answer{white-space:pre-wrap;line-height:1.55;min-height:130px}.answer{min-height:240px}.badge{float:right;background:#17213a;padding:8px 12px;border-radius:20px}\n</style></head><body><div class="wrap">\n<div class="badge" id="state">Ready</div><h1>Voice Answer Assistant</h1><div class="sub">Free Gemini AI backend • 5-minute capture</div>\n<div class="grid" style="margin-top:20px">\n<section class="card"><label>Backend URL</label><input id="backend" placeholder="Leave blank on Render">\n<div class="small" style="margin-top:8px">Gemini API key stays on the server.</div><hr style="border:0;border-top:1px solid #263554;margin:17px 0">\n<div class="timer" id="timer">05:00</div>\n<button id="micBtn">Start microphone</button><button id="stopBtn" class="danger" disabled>Stop</button><button id="shareBtn" class="secondary">Share tab/screen audio</button>\n<div class="status" id="status">Ready.</div><div class="small">Capture automatically stops after 5 minutes.</div></section>\n<section class="card"><label>Live transcript</label><div id="transcript" class="transcript">Your speech will appear here.</div>\n<button id="answerBtn">Get AI answer</button><button id="clearBtn" class="secondary">Clear</button></section>\n<section class="card" style="grid-column:1/-1"><label>AI answer</label><div id="answer" class="answer">AI answers will appear here.</div></section>\n</div></div>\n<script>\nconst $=id=>document.getElementById(id);let recorder=null,chunks=[],stream=null,displayStream=null,recognition=null,timerId=null,remaining=300,transcriptText="";\nfunction status(x,live=false){$("status").textContent=x;$("state").textContent=live?"Capturing":"Ready"}\nfunction fmt(s){return String(Math.floor(s/60)).padStart(2,"0")+":"+String(s%60).padStart(2,"0")}\nfunction reset(){remaining=300;$("timer").textContent=fmt(remaining)}\nfunction timer(){clearInterval(timerId);timerId=setInterval(()=>{remaining--;$("timer").textContent=fmt(Math.max(remaining,0));if(remaining<=0)stop()},1000)}\nfunction backend(){return ($("backend").value||"").trim().replace(/\\/+$/,"")||location.origin}\nasync function recog(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){status("Recording. Gemini will transcribe after recording.");return}\nrecognition=new SR();recognition.continuous=true;recognition.interimResults=true;recognition.lang="en-US";\nrecognition.onresult=e=>{let t="";for(let i=e.resultIndex;i<e.results.length;i++)t+=e.results[i][0].transcript+" ";transcriptText=t.trim();$("transcript").textContent=transcriptText||"Listening..."};\nrecognition.onend=()=>{if(recorder&&recorder.state==="recording")try{recognition.start()}catch(e){}};try{recognition.start()}catch(e){}}\nasync function start(){try{stream=await navigator.mediaDevices.getUserMedia({audio:true});chunks=[];recorder=new MediaRecorder(stream);\nrecorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};recorder.onstop=async()=>{if(recognition)try{recognition.stop()}catch(e){};await transcribe()};\nrecorder.start(1000);$("micBtn").disabled=true;$("stopBtn").disabled=false;reset();timer();status("Microphone capturing...",true);recog()}catch(e){status("Microphone could not start: "+e.message)}}\nasync function stop(){clearInterval(timerId);if(recorder&&recorder.state!=="inactive")recorder.stop();if(stream){stream.getTracks().forEach(t=>t.stop());stream=null}if(displayStream){displayStream.getTracks().forEach(t=>t.stop());displayStream=null}\n$("micBtn").disabled=false;$("stopBtn").disabled=true;status("Capture stopped. Processing audio...")}\nasync function transcribe(){if(!chunks.length)return;if(transcriptText.trim()){status("Browser transcript ready.");return}\ntry{const fd=new FormData();fd.append("audio",new Blob(chunks,{type:chunks[0].type||"audio/webm"}),"capture.webm");\nconst r=await fetch(backend()+"/api/transcribe",{method:"POST",body:fd});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||"Transcription failed");transcriptText=(d.text||"").trim();$("transcript").textContent=transcriptText||"No speech detected.";status("Gemini transcription complete.")}catch(e){status("Transcription failed: "+e.message)}}\nasync function answer(){const q=$("transcript").textContent.trim();if(!q||q==="Your speech will appear here."){status("Please speak first.");return}\n$("answer").textContent="Thinking...";try{const r=await fetch(backend()+"/api/answer",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:q})});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||"AI answer failed");$("answer").textContent=d.answer||"No answer returned.";status("AI answer ready.")}catch(e){$("answer").textContent="Error: "+e.message;status("AI answer failed.")}}\nasync function share(){try{displayStream=await navigator.mediaDevices.getDisplayMedia({video:true,audio:true});const a=displayStream.getAudioTracks();if(!a.length){status("Select a browser tab and enable Share audio.");return}\nchunks=[];transcriptText="";recorder=new MediaRecorder(new MediaStream(a));recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};recorder.onstop=transcribe;recorder.start(1000);\nreset();timer();$("stopBtn").disabled=false;$("micBtn").disabled=true;status("Shared tab/screen audio capturing...",true);displayStream.getVideoTracks()[0].onended=stop}catch(e){status("Screen sharing failed: "+e.message)}}\n$("micBtn").onclick=start;$("stopBtn").onclick=stop;$("shareBtn").onclick=share;$("answerBtn").onclick=answer;\n$("clearBtn").onclick=()=>{$("transcript").textContent="";$("answer").textContent="AI answers will appear here.";transcriptText="";reset();status("Cleared.")};reset();\n</script></body></html>'

def generate(parts):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured on the server.")
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    r=requests.post(url,params={"key":GEMINI_API_KEY},json={"contents":[{"parts":parts}]},timeout=120)
    if not r.ok: raise RuntimeError(r.text[:3000])
    d=r.json()
    return "".join(p.get("text","") for p in d.get("candidates",[{}])[0].get("content",{}).get("parts",[])).strip()

@app.get("/")
def index(): return Response(INDEX_HTML,mimetype="text/html")

@app.get("/health")
@app.get("/api/health")
def health(): return jsonify({"ok":True,"service":"voice-answer-assistant","gemini_key_configured":bool(GEMINI_API_KEY),"model":GEMINI_MODEL})

@app.get("/api/test-gemini")
def test():
    try: return jsonify({"ok":True,"message":generate([{"text":"Reply exactly: Connection successful."}] )})
    except Exception as e: return jsonify({"ok":False,"error":str(e)}),500

@app.get("/api/test-openai")
def old_test(): return test()

@app.post("/api/answer")
def answer():
    q=((request.get_json(silent=True) or {}).get("question") or "").strip()
    if not q:return jsonify({"ok":False,"error":"Question is empty."}),400
    try:return jsonify({"ok":True,"answer":generate([{"text":"You are a real-time voice answer assistant. Give concise, accurate, natural answers.\n\nUser question:\n"+q}])})
    except Exception as e:return jsonify({"ok":False,"error":str(e)}),500

@app.post("/api/transcribe")
def transcribe():
    f=request.files.get("audio")
    if not f:return jsonify({"ok":False,"error":"No audio file received."}),400
    raw=f.read()
    try:
        text=generate([{"text":"Transcribe this audio exactly. Return only the spoken words."},{"inlineData":{"mimeType":f.mimetype or "audio/webm","data":base64.b64encode(raw).decode()}}])
        return jsonify({"ok":True,"text":text})
    except Exception as e:return jsonify({"ok":False,"error":str(e)}),500

if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
