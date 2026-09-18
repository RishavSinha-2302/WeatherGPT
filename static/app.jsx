const { useState, useEffect, useRef } = React;

// Preset agricultural and regional locations
const PRESET_LOCATIONS = [
  { name: "Pune (Haveli / Baramati)", lat: 18.5204, lon: 73.8567 },
  { name: "Nashik (Grape Belt)", lat: 19.9975, lon: 73.7898 },
  { name: "Nagpur (Cotton & Citrus)", lat: 21.1458, lon: 79.0882 },
  { name: "Kolhapur (Sugarcane Belt)", lat: 16.7050, lon: 74.2433 },
  { name: "Mumbai (Coastal)", lat: 19.0760, lon: 72.8777 },
  { name: "Delhi NCR (Northern Plains)", lat: 28.6139, lon: 77.2090 },
];

const QUICK_PROMPTS = {
  en: [
    { title: "🌧️ Rain Today?", text: "Will it rain today in my field? Should I spray pesticides?" },
    { title: "🌱 7-Day Soil Moisture", text: "Give me the 7-day soil moisture and crop planting advisory." },
    { title: "🚨 Hazard Warning", text: "Are there any active weather hazard alerts or storm warnings here?" },
    { title: "💨 Wind & Temperature", text: "What is the current wind speed and temperature?" }
  ],
  hi: [
    { title: "🌧️ आज बारिश होगी?", text: "क्या आज मेरे खेत में बारिश होगी? क्या मैं कीटनाशक छिड़क सकता हूँ?" },
    { title: "🌱 7 दिन की मिट्टी नमी", text: "अगले 7 दिनों के लिए मिट्टी की नमी और फसल बुवाई की सलाह दें।" },
    { title: "🚨 मौसम चेतावनी", text: "क्या मेरे क्षेत्र में कोई आंधी-तूफान या भारी बारिश का अलर्ट है?" },
    { title: "💨 हवा और तापमान", text: "वर्तमान तापमान और हवा की गति कितनी है?" }
  ],
  mr: [
    { title: "🌧️ आज पाऊस पडेल का?", text: "आज माझ्या शेतात पाऊस पडेल का? मी कीटकनाशक फवारणी करावी का?" },
    { title: "🌱 7 दिवसांचा माती ओलावा", text: "पुढील 7 दिवसांतील जमिनीतील ओलावा आणि पीक पेरणी सल्ला द्या." },
    { title: "🚨 वादळाचा इशारा", text: "माझ्या परिसरात अतिवृष्टी किंवा वादळाचा काही इशारा आहे का?" },
    { title: "💨 वारा आणि तापमान", text: "सध्याचे तापमान आणि वाऱ्याचा वेग किती आहे?" }
  ]
};

// Helper function to render formatted text: transforms **text** to bold, formats bullets, and removes raw asterisks
const formatMessageContent = (text) => {
  if (!text) return null;
  const lines = text.split('\n');

  return lines.map((rawLine, idx) => {
    const line = rawLine.trim();

    if (!line) {
      return <div key={idx} className="h-2" />;
    }

    // Check if line is a bullet item (*, -, •)
    const isBullet = line.startsWith('* ') || line.startsWith('- ') || line.startsWith('• ');
    const content = isBullet ? line.slice(2).trim() : rawLine;

    // Parse **bold** parts: regex match anything inside **...**
    const parts = [];
    const boldRegex = /\*\*(.*?)\*\*/g;
    let lastIndex = 0;
    let match;

    while ((match = boldRegex.exec(content)) !== null) {
      if (match.index > lastIndex) {
        parts.push(content.substring(lastIndex, match.index));
      }
      parts.push(
        <strong key={`bold-${idx}-${match.index}`} className="font-bold text-white tracking-wide">
          {match[1]}
        </strong>
      );
      lastIndex = boldRegex.lastIndex;
    }

    if (lastIndex < content.length) {
      parts.push(content.substring(lastIndex));
    }

    // Strip any remaining unclosed or rogue ** asterisks
    const cleanedParts = parts.map((part) => {
      if (typeof part === 'string') {
        return part.replace(/\*\*/g, '').replace(/^\*\s*/, '');
      }
      return part;
    });

    if (isBullet) {
      return (
        <div key={idx} className="flex items-start space-x-2.5 my-1.5 pl-1">
          <span className="text-emerald-400 font-bold text-lg leading-relaxed select-none">•</span>
          <div className="flex-1 leading-relaxed text-slate-100">{cleanedParts}</div>
        </div>
      );
    }

    return (
      <p key={idx} className={idx > 0 ? "mt-2 leading-relaxed" : "leading-relaxed"}>
        {cleanedParts}
      </p>
    );
  });
};

function App() {
  const [messages, setMessages] = useState([
    {
      id: "welcome",
      sender: "assistant",
      text: "👋 Namaste! I am **WeatherGPT**.\nI route your weather queries to real-time Numerical Weather Prediction (NWP) models, 7-day soil moisture calculations, and WMO WIS 2.0 hazard warnings.\n\n🎙️ Press the **Microphone** to speak in **Hindi**, **Marathi**, or **English**!",
      tools_called: [],
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ]);
  const [inputText, setInputText] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [speakingMessageId, setSpeakingMessageId] = useState(null);
  const [selectedLanguage, setSelectedLanguage] = useState("en");
  const [location, setLocation] = useState({
    lat: 18.5204,
    lon: 73.8567,
    name: "Pune, Maharashtra",
    isGps: false
  });
  const [quickWeather, setQuickWeather] = useState(null);
  const [isSending, setIsSending] = useState(false);
  const [showLocationModal, setShowLocationModal] = useState(false);
  const [showAlertModal, setShowAlertModal] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(true);

  const messagesEndRef = useRef(null);
  const recognitionRef = useRef(null);
  const speechSynthRef = useRef(window.speechSynthesis);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    if (window.lucide) window.lucide.createIcons();
  }, [messages, isSending]);

  // Check Web Speech API support & Request Geolocation on mount
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setSpeechSupported(false);
    }

    // Try automatic GPS Geolocation
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const lat = parseFloat(pos.coords.latitude.toFixed(4));
          const lon = parseFloat(pos.coords.longitude.toFixed(4));
          setLocation({
            lat,
            lon,
            name: `GPS (${lat}°N, ${lon}°E)`,
            isGps: true
          });
          fetchQuickWeather(lat, lon);
        },
        (err) => {
          console.warn("GPS access denied or unavailable, using Pune default coordinates.", err);
          fetchQuickWeather(18.5204, 73.8567);
        },
        { enableHighAccuracy: true, timeout: 8000 }
      );
    } else {
      fetchQuickWeather(18.5204, 73.8567);
    }
  }, []);

  // Fetch quick weather and hazard snapshot
  const fetchQuickWeather = async (lat, lon) => {
    try {
      const res = await fetch(`/api/weather/quick?lat=${lat}&lon=${lon}`);
      if (res.ok) {
        const data = await res.json();
        setQuickWeather(data);
      }
    } catch (e) {
      console.error("Error fetching quick weather:", e);
    }
  };

  // Toggle Voice Recognition (STT)
  const toggleSpeechRecognition = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Web Speech API is not supported in this browser. Please use Chrome, Edge, or Safari.");
      return;
    }

    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognitionRef.current = recognition;
      recognition.continuous = false;
      recognition.interimResults = true;

      // Select speech recognition language
      if (selectedLanguage === "hi") recognition.lang = "hi-IN";
      else if (selectedLanguage === "mr") recognition.lang = "mr-IN";
      else recognition.lang = "en-IN";

      recognition.onstart = () => {
        setIsListening(true);
      };

      recognition.onresult = (event) => {
        let transcript = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }
        setInputText(transcript);
      };

      recognition.onerror = (event) => {
        console.error("Speech recognition error:", event.error);
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognition.start();
    } catch (err) {
      console.error("Error starting speech recognition:", err);
      setIsListening(false);
    }
  };

  // Text to Speech (TTS)
  const speakText = (text, messageId) => {
    if (!speechSynthRef.current) return;

    if (speakingMessageId === messageId) {
      speechSynthRef.current.cancel();
      setSpeakingMessageId(null);
      return;
    }

    speechSynthRef.current.cancel();

    // Clean markdown stars and emojis for cleaner speech audio
    const cleanText = text
      .replace(/\*\*/g, '')
      .replace(/[#_*`~]/g, '')
      .replace(/⚠️|🚨|🌧️|🌾|⛅|👋|🌱|💨|🚜/g, '');

    const utterance = new SpeechSynthesisUtterance(cleanText);
    
    // Choose voice language
    if (selectedLanguage === "hi") utterance.lang = "hi-IN";
    else if (selectedLanguage === "mr") utterance.lang = "mr-IN";
    else utterance.lang = "en-IN";

    utterance.rate = 0.95; // Slightly slower for clarity
    utterance.pitch = 1.0;

    utterance.onend = () => setSpeakingMessageId(null);
    utterance.onerror = () => setSpeakingMessageId(null);

    setSpeakingMessageId(messageId);
    speechSynthRef.current.speak(utterance);
  };

  // Send message to FastAPI /api/chat
  const handleSendMessage = async (textToSend) => {
    const query = (textToSend || inputText).trim();
    if (!query || isSending) return;

    // Stop speech synthesis if speaking
    if (speechSynthRef.current) {
      speechSynthRef.current.cancel();
      setSpeakingMessageId(null);
    }

    const userMsg = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: query,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMsg]);
    setInputText("");
    setIsSending(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: "user_farmer",
          message: query,
          lat: location.lat,
          lon: location.lon,
          language: selectedLanguage
        })
      });

      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }

      const data = await res.json();
      const botMsg = {
        id: `bot-${Date.now()}`,
        sender: "assistant",
        text: data.reply,
        tools_called: data.tools_called || [],
        model: data.model,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };

      setMessages(prev => [...prev, botMsg]);

      // Refresh quick weather card if tools brought fresh data
      fetchQuickWeather(location.lat, location.lon);

      // Auto-read response if user spoke via microphone
      if (isListening) {
        speakText(data.reply, botMsg.id);
      }
    } catch (err) {
      console.error("Chat error:", err);
      const errMsg = {
        id: `err-${Date.now()}`,
        sender: "assistant",
        text: "⚠️ An error occurred connecting to WeatherGPT backend. Please verify the server is running.",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setMessages(prev => [...prev, errMsg]);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="flex flex-col h-screen max-w-xl mx-auto bg-slate-900 border-x border-slate-800 shadow-2xl overflow-hidden" lang={selectedLanguage}>
      
      {/* 1. Header Bar (WhatsApp / Native App Style) */}
      <header className="bg-emerald-900/90 backdrop-blur-md px-4 py-3 border-b border-emerald-700/50 flex items-center justify-between z-20">
        <div className="flex items-center space-x-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center shadow-lg">
              <span className="text-xl">🌦️</span>
            </div>
            <span className="absolute bottom-0 right-0 w-3 h-3 bg-emerald-400 border-2 border-slate-900 rounded-full animate-ping"></span>
            <span className="absolute bottom-0 right-0 w-3 h-3 bg-emerald-400 border-2 border-slate-900 rounded-full"></span>
          </div>
          <div>
            <div className="flex items-center space-x-1.5">
              <h1 className="text-base sm:text-lg font-bold text-white tracking-tight">WeatherGPT</h1>
              <span className="text-[10px] bg-emerald-700/80 text-emerald-100 font-medium px-1.5 py-0.5 rounded">NWP AI</span>
            </div>
            <button 
              onClick={() => setShowLocationModal(true)}
              className="text-xs sm:text-sm text-emerald-200/90 hover:text-white flex items-center space-x-1 transition"
              title="Click to change location coordinates"
            >
              <span>📍 {location.name}</span>
              <span className="text-[10px] text-emerald-300">▼</span>
            </button>
          </div>
        </div>

        {/* Controls: Language Dropdown & Quick Status */}
        <div className="flex items-center space-x-2">
          <select
            value={selectedLanguage}
            onChange={(e) => setSelectedLanguage(e.target.value)}
            className="bg-emerald-950/80 border border-emerald-600/60 text-emerald-100 text-xs sm:text-sm rounded-lg px-2.5 py-1.5 font-medium focus:outline-none focus:ring-1 focus:ring-emerald-400 cursor-pointer"
            id="language-selector"
          >
            <option value="en">🇬🇧 English</option>
            <option value="hi">🇮🇳 हिन्दी</option>
            <option value="mr">🌾 मराठी</option>
          </select>
        </div>
      </header>

      {/* 2. Ambient Weather & Active Hazard Alert Pill */}
      {quickWeather && (
        <div className="bg-slate-950/90 border-b border-slate-800 px-4 py-2.5 flex items-center justify-between text-xs sm:text-sm">
          <div className="flex items-center space-x-3">
            <span className="flex items-center space-x-1 text-slate-200">
              <span className="text-amber-400">🌡️</span>
              <span className="font-semibold">{quickWeather.current?.temperature ?? '--'}°C</span>
            </span>
            <span className="text-slate-400">|</span>
            <span className="flex items-center space-x-1 text-slate-300">
              <span>💨</span>
              <span>{quickWeather.current?.wind_speed ?? '--'} km/h</span>
            </span>
          </div>
          
          {quickWeather.alerts?.active_alerts_count > 0 ? (
            <button
              onClick={() => setShowAlertModal(true)}
              className="flex items-center space-x-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 px-2.5 py-1 rounded-full border border-amber-500/40 transition cursor-pointer group"
              title="Click to view full severe weather warning bulletin"
              id="alert-pill-button"
            >
              <span className="animate-bounce">🚨</span>
              <span className="font-semibold">{quickWeather.alerts.active_alerts_count} Active Warning</span>
              <span className="text-[10px] bg-amber-400 text-slate-950 font-bold px-1.5 py-0.5 rounded-full ml-1 group-hover:bg-amber-300">View</span>
            </button>
          ) : (
            <div className="flex items-center space-x-1 text-emerald-400">
              <span>✓</span>
              <span>No severe hazard</span>
            </div>
          )}
        </div>
      )}

      {/* 2b. Expandable Alert Notification Strip */}
      {quickWeather?.alerts?.active_alerts_count > 0 && (
        <div 
          onClick={() => setShowAlertModal(true)}
          className="bg-amber-950/70 border-b border-amber-600/40 px-4 py-2 flex items-center justify-between text-xs sm:text-sm text-amber-200 cursor-pointer hover:bg-amber-900/70 transition"
          id="alert-banner-strip"
        >
          <div className="flex items-center space-x-2 truncate">
            <span className="text-sm">⚠️</span>
            <span className="font-medium truncate">
              {quickWeather.alerts.alerts?.[0]?.description || "Active Severe Weather Hazard in this region"}
            </span>
          </div>
          <span className="text-xs sm:text-sm underline text-amber-300 flex-shrink-0 ml-2 font-semibold">Read Details &rarr;</span>
        </div>
      )}

      {/* 3. Messages Chat Body */}
      <main className="flex-1 overflow-y-auto p-4 space-y-4 chat-pattern bg-slate-900/95">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}
          >
            <div
              className={`max-w-[90%] sm:max-w-[85%] rounded-2xl px-4 py-3 shadow-md relative group ${
                msg.sender === "user"
                  ? "bg-emerald-600 text-white rounded-br-none"
                  : "bg-slate-800/90 border border-slate-700/80 text-slate-100 rounded-bl-none"
              }`}
            >
              {/* Message Content with increased font size and parsed formatting */}
              <div className="text-[16px] sm:text-[17px] leading-[1.7] whitespace-pre-wrap">
                {formatMessageContent(msg.text)}
              </div>

              {/* Tool Execution Badges (SIH Hackathon feature demonstration) */}
              {msg.tools_called && msg.tools_called.length > 0 && (
                <div className="mt-3 pt-2.5 border-t border-slate-700/60 text-xs sm:text-[13px] space-y-1.5">
                  <div className="text-emerald-400 font-semibold flex items-center space-x-1">
                    <span>⚡ Numerical Prediction Tools Executed:</span>
                  </div>
                  {msg.tools_called.map((toolItem, tIdx) => (
                    <div key={tIdx} className="bg-slate-900/80 px-2.5 py-1.5 rounded-lg border border-slate-700/50 text-slate-300 flex items-center justify-between">
                      <code className="text-amber-300 font-mono text-xs">
                        {toolItem.tool}({Object.entries(toolItem.args || {}).map(([k,v]) => `${k}=${v}`).join(', ')})
                      </code>
                      <span className="text-[11px] bg-emerald-950 text-emerald-300 px-1.5 py-0.5 rounded font-semibold">NWP OK</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Footer with Timestamp and TTS Speaker Button (LLM model name removed) */}
              <div className="mt-2.5 flex items-center justify-between text-xs opacity-75 pt-1 border-t border-slate-700/40">
                <div className="flex items-center space-x-2 text-slate-400 text-xs">
                  <span>{msg.timestamp}</span>
                </div>

                {msg.sender === "assistant" && (
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => speakText(msg.text, msg.id)}
                      className={`px-2.5 py-1 rounded-full flex items-center space-x-1.5 text-xs sm:text-[13px] font-medium transition ${
                        speakingMessageId === msg.id
                          ? "bg-amber-400 text-slate-950 font-bold animate-pulse"
                          : "bg-slate-700/80 hover:bg-slate-600 text-slate-200"
                      }`}
                      title="Speak response in selected regional language"
                      id={`speak-btn-${msg.id}`}
                    >
                      <span>{speakingMessageId === msg.id ? "🔊 Stop" : "🔈 Speak"}</span>
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}

        {/* Loading Indicator */}
        {isSending && (
          <div className="flex items-center space-x-2 text-xs sm:text-sm text-emerald-400 bg-slate-800/80 w-fit px-3.5 py-2.5 rounded-2xl border border-slate-700">
            <div className="flex space-x-1">
              <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce"></div>
              <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce [animation-delay:0.2s]"></div>
              <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce [animation-delay:0.4s]"></div>
            </div>
            <span>Fetching Numerical Weather Prediction & Hazard Polygons...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </main>

      {/* 4. Quick Agricultural Suggestions Chips */}
      <div className="bg-slate-950/80 px-3 py-2 border-t border-slate-800/80 overflow-x-auto flex space-x-2 scrollbar-none">
        {(QUICK_PROMPTS[selectedLanguage] || QUICK_PROMPTS.en).map((chip, idx) => (
          <button
            key={idx}
            onClick={() => handleSendMessage(chip.text)}
            className="flex-shrink-0 bg-slate-800/90 hover:bg-emerald-900/60 border border-slate-700/80 hover:border-emerald-500/60 text-slate-200 text-xs sm:text-sm font-medium px-3.5 py-2 rounded-full transition whitespace-nowrap shadow-sm"
          >
            {chip.title}
          </button>
        ))}
      </div>

      {/* 5. Voice & Text Input Bottom Bar */}
      <footer className="bg-slate-950 px-3 py-3 border-t border-slate-800 flex flex-col space-y-2">
        {/* Active Speech Waveform Indicator */}
        {isListening && (
          <div className="flex items-center justify-center space-x-2 bg-emerald-950/90 border border-emerald-500/50 py-1.5 px-3 rounded-xl text-emerald-200 text-xs sm:text-sm">
            <div className="flex items-center space-x-1">
              <span className="w-1 bg-emerald-400 wave-bar"></span>
              <span className="w-1 bg-emerald-400 wave-bar"></span>
              <span className="w-1 bg-emerald-400 wave-bar"></span>
              <span className="w-1 bg-emerald-400 wave-bar"></span>
              <span className="w-1 bg-emerald-400 wave-bar"></span>
            </div>
            <span className="font-semibold">
              {selectedLanguage === "hi" ? "सुन रहा हूँ... बोलिए" : selectedLanguage === "mr" ? "ऐकत आहे... बोला" : "Listening to your voice..."}
            </span>
          </div>
        )}

        <div className="flex items-center space-x-2">
          {/* Microphone Button (Speech-to-Text) */}
          <button
            onClick={toggleSpeechRecognition}
            className={`w-12 h-12 rounded-full flex items-center justify-center text-xl transition-all shadow-lg flex-shrink-0 ${
              isListening
                ? "bg-rose-600 text-white recording-pulse"
                : "bg-emerald-600 hover:bg-emerald-500 text-white"
            }`}
            title="Press and speak in your language"
            id="mic-button"
          >
            {isListening ? "⏹️" : "🎙️"}
          </button>

          {/* Text Input with enlarged readable font */}
          <div className="flex-1 relative">
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
              placeholder={
                selectedLanguage === "hi"
                  ? "मौसम या फसल के बारे में पूछें..."
                  : selectedLanguage === "mr"
                  ? "हवामान किंवा पिकाबद्दल विचारा..."
                  : "Ask about rain, soil moisture, alerts..."
              }
              className="w-full bg-slate-900 border border-slate-700/80 rounded-2xl px-4 py-3 text-base sm:text-[17px] text-slate-100 placeholder-slate-400 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition"
              id="chat-input"
            />
          </div>

          {/* Send Button */}
          <button
            onClick={() => handleSendMessage()}
            disabled={!inputText.trim() || isSending}
            className="w-12 h-12 rounded-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:hover:bg-emerald-600 text-white flex items-center justify-center transition shadow-lg flex-shrink-0"
            id="send-button"
            title="Send query"
          >
            <span className="text-lg">➤</span>
          </button>
        </div>
      </footer>

      {/* 6. Geolocation & Spatial Coordinate Selector Modal */}
      {showLocationModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-5 max-w-sm w-full space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-white text-base flex items-center space-x-1.5">
                <span>📍</span>
                <span>Select Weather Station / Region</span>
              </h3>
              <button
                onClick={() => setShowLocationModal(false)}
                className="text-slate-400 hover:text-white text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-slate-300">
              Select an agricultural cluster or enter custom GPS coordinates for localized NWP modeling and PostGIS alert intersection:
            </p>

            {/* Presets */}
            <div className="space-y-1.5 max-h-48 overflow-y-auto">
              {PRESET_LOCATIONS.map((loc, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    setLocation({ ...loc, isGps: false });
                    fetchQuickWeather(loc.lat, loc.lon);
                    setShowLocationModal(false);
                  }}
                  className={`w-full text-left px-3 py-2 rounded-xl text-xs flex items-center justify-between transition ${
                    location.name === loc.name
                      ? "bg-emerald-950 border border-emerald-500 text-emerald-200 font-semibold"
                      : "bg-slate-800/80 hover:bg-slate-700/80 text-slate-200 border border-slate-700/50"
                  }`}
                >
                  <span>{loc.name}</span>
                  <span className="font-mono text-[10px] text-slate-400">
                    {loc.lat}°N, {loc.lon}°E
                  </span>
                </button>
              ))}
            </div>

            {/* Custom Lat / Lon Inputs */}
            <div className="pt-2 border-t border-slate-800 flex space-x-2">
              <input
                type="number"
                step="0.0001"
                value={location.lat}
                onChange={(e) => setLocation(prev => ({ ...prev, lat: parseFloat(e.target.value) || 0, name: "Custom Coordinate" }))}
                placeholder="Latitude"
                className="w-1/2 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white"
              />
              <input
                type="number"
                step="0.0001"
                value={location.lon}
                onChange={(e) => setLocation(prev => ({ ...prev, lon: parseFloat(e.target.value) || 0, name: "Custom Coordinate" }))}
                placeholder="Longitude"
                className="w-1/2 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white"
              />
            </div>

            <button
              onClick={() => {
                fetchQuickWeather(location.lat, location.lon);
                setShowLocationModal(false);
              }}
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-medium py-2 rounded-xl text-xs transition"
            >
              Apply Coordinates & Refresh NWP
            </button>
          </div>
        </div>
      )}

      {/* 7. Hazard Warning Details Modal */}
      {showAlertModal && quickWeather?.alerts && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-amber-500/60 rounded-2xl p-5 max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <span className="text-2xl">🚨</span>
                <div>
                  <h3 className="font-bold text-white text-base">Active Weather Hazard Warning</h3>
                  <span className="text-[10px] text-amber-400 font-mono uppercase tracking-wider">
                    WMO WIS 2.0 / PostGIS Spatial Intersection
                  </span>
                </div>
              </div>
              <button
                onClick={() => setShowAlertModal(false)}
                className="text-slate-400 hover:text-white text-lg font-bold p-1"
                id="close-alert-modal"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 max-h-72 overflow-y-auto pr-1">
              {quickWeather.alerts.alerts && quickWeather.alerts.alerts.length > 0 ? (
                quickWeather.alerts.alerts.map((alert, idx) => (
                  <div key={idx} className="bg-amber-950/50 border border-amber-500/30 rounded-xl p-3.5 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold uppercase px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                        {alert.severity || 'Severe'}
                      </span>
                      <span className="text-[10px] text-slate-400">
                        Source: {alert.source || 'IMD / WIS 2.0'}
                      </span>
                    </div>
                    <p className="text-sm text-slate-100 font-medium leading-relaxed">
                      {alert.description}
                    </p>
                    <div className="text-[11px] text-slate-400 flex items-center justify-between pt-1 border-t border-amber-500/20">
                      <span>Valid: {alert.active_until || 'Next 48 Hours'}</span>
                      <span className="text-emerald-400 font-mono text-[10px]">Lat {quickWeather.alerts.latitude}°N, Lon {quickWeather.alerts.longitude}°E</span>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-300">No details available.</p>
              )}
            </div>

            {/* Farm Safety Advice */}
            <div className="bg-slate-800/80 rounded-xl p-3 text-xs text-slate-300 space-y-1 border border-slate-700">
              <div className="font-semibold text-emerald-400 flex items-center space-x-1">
                <span>🛡️ Recommended Farm Safety Actions:</span>
              </div>
              <p>• Defer pesticide spraying and fertilizer application during high winds/rain.</p>
              <p>• Ensure proper trenching & drainage in fields to avoid standing water.</p>
              <p>• Secure loose shed roofing and move cattle to sheltered structures.</p>
            </div>

            <div className="flex space-x-2 pt-1">
              <button
                onClick={() => {
                  setShowAlertModal(false);
                  handleSendMessage(
                    selectedLanguage === "hi" 
                      ? "इस मौसम चेतावनी से बचने के लिए किसान क्या करें?"
                      : selectedLanguage === "mr"
                      ? "या हवामान इशाऱ्यापासून पिकांचे संरक्षण करण्यासाठी काय करावे?"
                      : "What farm safety precautions should I take for this weather warning?"
                  );
                }}
                className="flex-1 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold py-2 rounded-xl text-xs transition flex items-center justify-center space-x-1 shadow-md"
              >
                <span>💬 Ask AI for Crop Protection Plan</span>
              </button>
              <button
                onClick={() => setShowAlertModal(false)}
                className="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded-xl text-xs font-medium transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
