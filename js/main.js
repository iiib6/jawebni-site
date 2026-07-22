/* ============================================================
   جاوبني — خيط الجواب
   مشهد افتتاحي مربوط بالتمرير: النقطة المعيّنة تسافر على الخيط
   الذهبي حتى تكمل الحرف «ح» فيصير «ج»، وبعدها يظهر الاسم كاملاً.
   ============================================================ */

gsap.registerPlugin(ScrollTrigger, MotionPathPlugin);

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const GOLD = "#C4A35A";

const thread = document.getElementById("thread");
const milestonesGroup = document.getElementById("milestones");
const dot = document.getElementById("dot");
const letter = document.getElementById("letter");

// موضع نقطة الجيم مُقاس من خط Reem Kufi نفسه:
// إزاحة -0.0375em أفقياً و +0.0775em عمودياً عن مرساة النص
const DOT_OFFSET_EM = { x: -0.0375, y: 0.0775 };
const MILESTONE_FRACTIONS = [0.3, 0.55, 0.78];

/* ---------- غرزة التطريز بالتذييل ---------- */

const stitchRow = document.getElementById("stitch-row");
const stitchEls = [];
for (let i = 0; i < 13; i++) {
  const cx = 20 + i * 43.3;
  const d = document.createElementNS("http://www.w3.org/2000/svg", "path");
  d.setAttribute("d", `M${cx - 7} 12 L${cx} 5 L${cx + 7} 12 L${cx} 19 Z`);
  d.setAttribute("class", "stitch");
  stitchRow.appendChild(d);
  stitchEls.push(d);
}

/* ---------- تقسيم الاقتباس إلى كلمات ---------- */

const quote = document.getElementById("quote");
quote.innerHTML = quote.textContent
  .trim()
  .split(/\s+/)
  .map((w) => `<span class="q-word">${w}</span>`)
  .join(" ");

/* ---------- بناء مشهد البطل حسب حجم الشاشة ---------- */

const mm = gsap.matchMedia();

mm.add(
  {
    isMobile: "(max-width: 760px)",
    isDesktop: "(min-width: 761px)",
  },
  (ctx) => {
    const { isMobile } = ctx.conditions;

    // إحداثيات المشهد داخل viewBox 1440×900 (مع القصّ slice تبقى
    // النافذة المرئية على الموبايل تقريباً x:512-928)
    const cfg = isMobile
      ? {
          anchorX: 720,
          anchorY: 580,
          fontSize: 340,
          d: "M 340 160 C 520 40, 740 90, 800 240 C 840 340, 620 440, 650 540 C 662 580, 685 595, 707 606",
        }
      : {
          anchorX: 880,
          anchorY: 600,
          fontSize: 560,
          d: "M -80 300 C 180 110, 430 130, 630 300 C 740 400, 600 580, 720 660 C 790 710, 829 703, 859 643",
        };

    const DOT_END = {
      x: cfg.anchorX + DOT_OFFSET_EM.x * cfg.fontSize,
      y: cfg.anchorY + DOT_OFFSET_EM.y * cfg.fontSize,
    };

    // حجم النقطة نسبي لحجم الحرف (نقطة الخط = ‎0.115em‎)
    const dotScale = cfg.fontSize / 560;
    gsap.set(".dot-core", { scale: dotScale });
    gsap.set(".dot-glow", { scale: dotScale });

    letter.setAttribute("x", cfg.anchorX);
    letter.setAttribute("y", cfg.anchorY);
    letter.style.fontSize = cfg.fontSize + "px";

    thread.setAttribute("d", cfg.d);
    const threadLength = thread.getTotalLength();
    thread.style.strokeDasharray = threadLength;
    thread.style.strokeDashoffset = reduceMotion ? 0 : threadLength;

    milestonesGroup.innerHTML = "";
    const milestoneEls = MILESTONE_FRACTIONS.map((f) => {
      const pt = thread.getPointAtLength(threadLength * f);
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("transform", `translate(${pt.x}, ${pt.y})`);
      const diamond = document.createElementNS("http://www.w3.org/2000/svg", "path");
      diamond.setAttribute("d", "M0 -13 L13 0 L0 13 L-13 0 Z");
      diamond.setAttribute("class", "milestone");
      g.appendChild(diamond);
      milestonesGroup.appendChild(g);
      return diamond;
    });

    /* مسار «تقليل الحركة»: مشهد مكتمل ساكن */
    if (reduceMotion) {
      gsap.set(dot, { x: DOT_END.x, y: DOT_END.y });
      gsap.set(milestoneEls, { scale: 1, opacity: 1, fill: GOLD });
      gsap.set(".hero__svg", { autoAlpha: 0.08 });
      gsap.set([".hero__wordmark", ".hero__tagline", ".hero__sub"], { autoAlpha: 1 });
      gsap.set(".hero__cue", { autoAlpha: 0 });
      return;
    }

    const startPt = thread.getPointAtLength(0);
    gsap.set(dot, { x: startPt.x, y: startPt.y });
    gsap.set(milestoneEls, { scale: 0.45, opacity: 0.28 });
    gsap.set(".hero__svg", { clearProps: "all" });

    const heroTl = gsap.timeline({
      defaults: { ease: "none" },
      scrollTrigger: {
        trigger: ".hero",
        start: "top top",
        end: "+=380%",
        scrub: 1,
        pin: ".hero__stage",
        anticipatePin: 1,
      },
    });

    heroTl
      // إشارة التمرير تختفي أول ما نتحرك
      .to(".hero__cue", { autoAlpha: 0, duration: 0.05 }, 0)
      // الخيط ينرسم والنقطة تسافر عليه
      .to(thread, { strokeDashoffset: 0, duration: 0.75 }, 0)
      .to(
        dot,
        {
          motionPath: { path: thread, align: thread, alignOrigin: [0.5, 0.5] },
          duration: 0.75,
        },
        0
      );

    // المعيّنات تضوّي لما النقطة تعبرها
    MILESTONE_FRACTIONS.forEach((f, i) => {
      heroTl.to(
        milestoneEls[i],
        { scale: 1, opacity: 1, fill: GOLD, duration: 0.04, ease: "back.out(2.5)" },
        0.75 * f - 0.02
      );
    });

    heroTl
      // لحظة الوصول: النقطة المعيّنة تنحط بمكانها — الحرف يكتمل ويصير «ج»
      .fromTo(
        ".dot-core",
        { scale: dotScale },
        { scale: dotScale * 1.22, duration: 0.02, ease: "power2.out", yoyo: true, repeat: 1 },
        0.75
      )
      .fromTo(
        ".dot-glow",
        { opacity: 0.7, scale: dotScale * 0.4 },
        { opacity: 0, scale: dotScale * 1.7, duration: 0.09, ease: "power1.out" },
        0.75
      )
      // الحرف المكتمل يرجع للخلفية — يصير «الحرف الشاهد»
      .to(".hero__svg", { autoAlpha: 0.08, scale: 1.15, duration: 0.12, ease: "power1.inOut" }, 0.84)
      // الاسم الكامل يظهر
      .fromTo(
        ".hero__wordmark",
        { y: 80, autoAlpha: 0 },
        { y: 0, autoAlpha: 1, duration: 0.1, ease: "power2.out" },
        0.86
      )
      .fromTo(
        ".hero__tagline",
        { y: 40, autoAlpha: 0 },
        { y: 0, autoAlpha: 1, duration: 0.08, ease: "power2.out" },
        0.9
      )
      .fromTo(
        ".hero__sub",
        { y: 30, autoAlpha: 0 },
        { y: 0, autoAlpha: 1, duration: 0.07, ease: "power2.out" },
        0.93
      );
  }
);

/* ---------- بقية الصفحة ---------- */

if (reduceMotion) {
  gsap.set(".thread-divider", { scaleX: 1 });
  gsap.set(".nav", { y: 0 });
  gsap.set(stitchEls, { scale: 1, opacity: 1 });
} else {
  /* التمرير الناعم */
  window.lenis = new Lenis({ duration: 1.15, smoothWheel: true });
  window.lenis.on("scroll", ScrollTrigger.update);
  gsap.ticker.add((time) => window.lenis.raf(time * 1000));
  gsap.ticker.lagSmoothing(0);

  /* روابط الأقسام تمشي بنفس التمرير الناعم */
  document.querySelectorAll('a[href^="#"]').forEach((a) => {
    a.addEventListener("click", (e) => {
      const target = document.querySelector(a.getAttribute("href"));
      if (target) {
        e.preventDefault();
        window.lenis.scrollTo(target);
      }
    });
  });

  /* شريط التنقّل يظهر بعد المشهد الافتتاحي */
  const navShow = gsap.to(".nav", { y: 0, duration: 0.5, ease: "power2.out", paused: true });
  ScrollTrigger.create({
    trigger: ".problem",
    start: "top 85%",
    onEnter: () => navShow.play(),
    onLeaveBack: () => navShow.reverse(),
  });

  /* المشكلة: الاقتباس كلمة كلمة */
  gsap.fromTo(
    ".q-word",
    { opacity: 0.12 },
    {
      opacity: 1,
      stagger: 0.08,
      ease: "none",
      scrollTrigger: {
        trigger: ".problem__quote",
        start: "top 78%",
        end: "bottom 42%",
        scrub: 0.6,
      },
    }
  );

  gsap.utils.toArray(".thread-divider").forEach((el) => {
    gsap.fromTo(
      el,
      { scaleX: 0 },
      {
        scaleX: 1,
        ease: "none",
        scrollTrigger: { trigger: el, start: "top 88%", end: "top 58%", scrub: 0.6 },
      }
    );
  });

  gsap.utils.toArray([".problem__body", ".problem__kicker"]).forEach((el) => {
    gsap.fromTo(
      el,
      { y: 40, autoAlpha: 0 },
      {
        y: 0,
        autoAlpha: 1,
        ease: "power1.out",
        scrollTrigger: { trigger: el, start: "top 88%", end: "top 62%", scrub: 0.8 },
      }
    );
  });

  /* الفيلم: بارالاكس + ظهور النص */
  gsap.fromTo(
    ".film__video",
    { yPercent: -6 },
    {
      yPercent: 6,
      ease: "none",
      scrollTrigger: { trigger: ".film", start: "top bottom", end: "bottom top", scrub: true },
    }
  );

  gsap.fromTo(
    ".film__title",
    { y: 70, autoAlpha: 0 },
    {
      y: 0,
      autoAlpha: 1,
      ease: "power1.out",
      scrollTrigger: { trigger: ".film__content", start: "top 75%", end: "top 40%", scrub: 0.8 },
    }
  );

  gsap.fromTo(
    ".film__body",
    { y: 60, autoAlpha: 0 },
    {
      y: 0,
      autoAlpha: 1,
      ease: "power1.out",
      scrollTrigger: { trigger: ".film__content", start: "top 62%", end: "top 30%", scrub: 0.8 },
    }
  );

  /* الخطوات: الخيط يمر على الغرزات الثلاث */
  const stepsLine = document.getElementById("steps-line");
  const stepsLen = 1200;
  stepsLine.style.strokeDasharray = stepsLen;
  stepsLine.style.strokeDashoffset = stepsLen;

  gsap.to(stepsLine, {
    strokeDashoffset: 0,
    ease: "none",
    scrollTrigger: { trigger: ".steps__track", start: "top 78%", end: "top 30%", scrub: 0.6 },
  });

  gsap.utils.toArray(".step").forEach((step, i) => {
    gsap.fromTo(
      step,
      { y: 50, autoAlpha: 0 },
      {
        y: 0,
        autoAlpha: 1,
        ease: "power1.out",
        scrollTrigger: {
          trigger: ".steps__track",
          start: `top ${74 - i * 10}%`,
          end: `top ${44 - i * 10}%`,
          scrub: 0.8,
        },
      }
    );
  });

  /* الميزات */
  gsap.utils.toArray(".feature").forEach((el) => {
    gsap.fromTo(
      el,
      { y: 44, autoAlpha: 0 },
      {
        y: 0,
        autoAlpha: 1,
        ease: "power1.out",
        scrollTrigger: { trigger: el, start: "top 86%", end: "top 60%", scrub: 0.8 },
      }
    );
  });

  /* الحرف الشاهد يتنفّس مع التمرير */
  gsap.utils.toArray([".features__witness", ".cta__witness"]).forEach((el) => {
    gsap.fromTo(
      el,
      { yPercent: -7 },
      {
        yPercent: 7,
        ease: "none",
        scrollTrigger: {
          trigger: el.parentElement,
          start: "top bottom",
          end: "bottom top",
          scrub: true,
        },
      }
    );
  });

  /* الدعوة */
  gsap.fromTo(
    ".cta__content",
    { y: 60, autoAlpha: 0, scale: 0.97 },
    {
      y: 0,
      autoAlpha: 1,
      scale: 1,
      ease: "power1.out",
      scrollTrigger: { trigger: ".cta", start: "top 72%", end: "top 34%", scrub: 0.8 },
    }
  );

  /* غرزة التذييل */
  gsap.set(stitchEls, { scale: 0, transformOrigin: "center", opacity: 0 });
  ScrollTrigger.create({
    trigger: ".footer",
    start: "top 92%",
    onEnter: () =>
      gsap.to(stitchEls, {
        scale: 1,
        opacity: 1,
        duration: 0.5,
        stagger: 0.05,
        ease: "back.out(2)",
      }),
    once: true,
  });
}

/* ---------- بعد تحميل الخطوط: إعادة حساب المواضع ---------- */

if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(() => ScrollTrigger.refresh());
}

/* ============================================================
   جاوبني — نافذة المحادثة التجريبية (Demo Chat Widget)
   ============================================================ */

(function () {
  const templates = {
    clinic: {
      name: "عيادة طبية / مركز تجميل",
      desc: "حجوزات ومواعيد واستشارات أوتوماتيكية",
      typeLabel: "العيادة"
    },
    restaurant: {
      name: "مطعم أو كافية",
      desc: "طلبات، حجز طاولات، وإجابة مكررة",
      typeLabel: "المطعم"
    },
    other: {
      name: "عمل آخر / شركة تجارية",
      desc: "أتمتة خدمة عملاء متكاملة",
      typeLabel: "المشروع"
    }
  };

  let activeBiz = {
    name: "",
    visitorName: "",
    bizType: "",
    tKey: ""
  };

  let chatState = "greeting"; // greeting | simulation | lead_capture | success
  let conversationHistory = [];
  let isWaitingForResponse = false;

  // DOM Elements
  const demoModal = document.getElementById("demoModal");
  const demoModalBackdrop = document.getElementById("demoModalBackdrop");
  const closeDemoModal = document.getElementById("closeDemoModal");
  const startDemoBtn = document.getElementById("startDemoBtn");
  const restartDemoBtns = document.querySelectorAll("#restartDemoBtn");
  
  const demoConfigScreen = document.getElementById("demoConfigScreen");
  const demoChatScreen = document.getElementById("demoChatScreen");
  const demoSuccessScreen = document.getElementById("demoSuccessScreen");
  
  const demoChatBody = document.getElementById("demoChatBody");
  const demoQuickReplies = document.getElementById("demoQuickReplies");
  const demoChatInput = document.getElementById("demoChatInput");
  const demoChatSendBtn = document.getElementById("demoChatSendBtn");
  
  const chatBizName = document.getElementById("chatBizName");
  const chatAvatar = document.getElementById("chatAvatar");
  
  const visitorNameInput = document.getElementById("visitorName");

  // Prevent Lenis / iOS body scroll lock from swallowing modal touch scrolling
  const demoModalCard = document.querySelector(".demo-modal__card");
  if (demoModalCard) {
    demoModalCard.addEventListener("touchmove", (e) => {
      e.stopPropagation();
    }, { passive: true });
  }
  const customBizNameInput = document.getElementById("customBizName");
  const templateButtons = document.querySelectorAll(".demo-template-btn");

  // Event Listeners for Opening Modal
  const openTriggers = document.querySelectorAll('.nav__cta, .cta__button');
  openTriggers.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      openModal();
    });
  });

  function openModal() {
    demoModal.style.display = "flex";
    document.body.style.overflow = "hidden";
    if (window.lenis) window.lenis.stop();
    
    // animate in
    gsap.killTweensOf(demoModal);
    gsap.killTweensOf(".demo-modal__card");
    
    gsap.set(demoModal, { opacity: 0 });
    gsap.set(".demo-modal__card", { y: 30, scale: 0.95 });
    
    demoModal.classList.add("active");
    gsap.to(demoModal, { opacity: 1, duration: 0.35, ease: "power2.out" });
    gsap.to(".demo-modal__card", { y: 0, scale: 1, duration: 0.45, ease: "back.out(1.2)" });
    
    showScreen("demoConfigScreen");
    resetForm();
  }

  function closeModal() {
    gsap.to(demoModal, { opacity: 0, duration: 0.3, ease: "power2.in", onComplete: () => {
      demoModal.style.display = "none";
      demoModal.classList.remove("active");
      document.body.style.overflow = "";
      if (window.lenis) window.lenis.start();
    }});
    gsap.to(".demo-modal__card", { y: 20, scale: 0.96, duration: 0.3, ease: "power2.in" });
  }

  if (closeDemoModal) closeDemoModal.addEventListener("click", closeModal);
  if (demoModalBackdrop) demoModalBackdrop.addEventListener("click", closeModal);

  // Escape key to close modal (#14)
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && demoModal.classList.contains("active")) {
      closeModal();
    }
  });

  // Focus trap inside modal (#8)
  if (demoModal) {
    demoModal.addEventListener("keydown", (e) => {
      if (e.key !== "Tab" || !demoModal.classList.contains("active")) return;
      const focusable = demoModal.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });
  }

  // Switch Screen Helper
  function showScreen(screenId) {
    demoConfigScreen.style.display = "none";
    demoChatScreen.style.display = "none";
    demoSuccessScreen.style.display = "none";
    
    const screen = document.getElementById(screenId);
    if (screen) screen.style.display = "flex";
  }

  // Reset form inputs
  function resetForm() {
    if (visitorNameInput) visitorNameInput.value = "";
    if (customBizNameInput) customBizNameInput.value = "";
    isWaitingForResponse = false;
    if (startDemoBtn) {
      startDemoBtn.disabled = false;
      startDemoBtn.textContent = "ابدأ الدردشة مع علي";
    }
    // reset templates selection
    templateButtons.forEach(btn => btn.classList.remove("active"));
    if (templateButtons.length > 0) templateButtons[0].classList.add("active");
  }

  // Handle template selection click
  templateButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      templateButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });

  // Start demo simulation
  if (startDemoBtn) {
    startDemoBtn.addEventListener("click", () => {
      if (isWaitingForResponse) return;
      isWaitingForResponse = true;
      startDemoBtn.disabled = true;
      startDemoBtn.textContent = "جاري التحميل...";

      const activeBtn = document.querySelector(".demo-template-btn.active");
      const vName = visitorNameInput ? visitorNameInput.value.trim() : "";
      const cName = customBizNameInput ? customBizNameInput.value.trim() : "";
      
      const tKey = activeBtn ? activeBtn.getAttribute("data-template") : "clinic";
      const tData = templates[tKey];
      
      activeBiz.tKey = tKey;
      activeBiz.visitorName = vName || "صديقي";
      activeBiz.name = cName || "مشروعك";
      activeBiz.bizType = tData.typeLabel;

      // Update Chat Header details (Always Ali - Smart Automation Partner)
      chatBizName.textContent = "علي — مستشار الأتمتة الذكي";
      chatAvatar.textContent = "ع";

      // Start Chat
      showScreen("demoChatScreen");
      initiateChatConversation();
    });
  }

  // Restart buttons (to try another business)
  restartDemoBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      showScreen("demoConfigScreen");
      resetForm();
    });
  });

  // Confirm booking button (replaced mailto link)
  const confirmBookingBtn = document.getElementById("confirmBookingBtn");
  if (confirmBookingBtn) {
    confirmBookingBtn.addEventListener("click", () => {
      submitLeadToServer();
      alert("تم تسجيل حجزك بنجاح! سنتواصل معك قريباً.");
      closeModal();
    });
  }

  // Chat message rendering helpers
  function sanitizeText(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function addMessage(text, isUser = false) {
    const msg = document.createElement("div");
    msg.className = `chat-message chat-message--${isUser ? 'user' : 'bot'}`;
    msg.innerHTML = sanitizeText(text).replace(/\n/g, "<br>");
    demoChatBody.appendChild(msg);
    demoChatBody.scrollTop = demoChatBody.scrollHeight;
  }

  let typingIndicatorEl = null;

  function showTypingIndicator() {
    if (typingIndicatorEl) return;
    
    typingIndicatorEl = document.createElement("div");
    typingIndicatorEl.className = "typing-indicator";
    typingIndicatorEl.innerHTML = "<span></span><span></span><span></span>";
    demoChatBody.appendChild(typingIndicatorEl);
    demoChatBody.scrollTop = demoChatBody.scrollHeight;
  }

  function hideTypingIndicator() {
    if (typingIndicatorEl) {
      typingIndicatorEl.remove();
      typingIndicatorEl = null;
    }
  }

  // Initial greeting message (Dynamic based on selected template)
  function initiateChatConversation() {
    demoChatBody.innerHTML = "";
    if (demoQuickReplies) demoQuickReplies.innerHTML = "";
    chatState = "greeting";

    let greetingText = "";
    if (activeBiz.tKey === "clinic") {
      greetingText = `أهلاً بك عيوني! باجر السبت متوفر دكتور أحمد بالأوقات التالية: الساعة 2:00 ظهراً، الساعة 3:00 العصر، والساعة 4:00 عصراً. يا وقت يناسبك أكتر؟ 🗓️✨`;
    } else if (activeBiz.tKey === "restaurant") {
      greetingText = `أهلاً بك في مطعم الديرة! السيستم مالتنا جاهز ياخذ طلبك تلقائياً وبأسرع وقت. جرب اطلب كباب أو اسأل عن خدمة التوصيل وشوف الرد التلقائي السريع. 🍔🍟`;
    } else {
      greetingText = `أهلاً بك! أنا المساعد الافتراضي لشركة "${activeBiz.name}". أستطيع الإجابة على استفسارات العملاء وحجز موعد استشاري أو مكالمة استكشافية. كيف أقدر أساعدك اليوم؟ 💼✨`;
    }
    
    // Reset history with the greeting message
    conversationHistory = [
      {
        role: "model",
        parts: [{ text: greetingText }]
      }
    ];

    showTypingIndicator();
    setTimeout(() => {
      hideTypingIndicator();
      addMessage(greetingText);
      isWaitingForResponse = false;
    }, 1200);
  }

  // Handle incoming user message
  function handleUserMessage(text) {
    // Add user message immediately
    addMessage(text, true);
    if (demoQuickReplies) demoQuickReplies.innerHTML = "";

    showTypingIndicator();
    
    // Call our server endpoint
    callRealGeminiAI(text);
  }

  // Real-time Gemini API calling through local backend /api/chat
  function callRealGeminiAI(userMessage) {
    // Add to history
    conversationHistory.push({
      role: "user",
      parts: [{ text: userMessage }]
    });

    const sysInstructions = {
      clinic: `# Identity & Role:
You are the advanced AI Virtual Assistant for a dental clinic named "Dental Care". Your primary goal is to provide a live, flawless, and impressive interactive demo for visitors of our AI automation platform "Jawabny". You must demonstrate to the user how the system handles bookings intelligently, adapts in real-time, and responds with human-like agility.

# Tone & Language Style:
- ALWAYS respond in friendly, professional, and natural Iraqi Arabic (العامية العراقية) just like a smart clinic receptionist.
- Use context-appropriate emojis (e.g., 🦷, ✨, 🗓️, 👍) to keep the chat engaging.
- Never mention that you are a "demo", a "test", or an "AI model built by Jawabny". Act as the actual clinic system.
- Keep responses concise, scannable, and interactive. Avoid long blocks of text.

# Simulation Rules & Dynamic Scheduling (CRITICAL):
You have a mock schedule for tomorrow, Saturday.
- Available slots at first: 2:00 PM and 4:00 PM.
- The 3:00 PM slot is the "Trap Slot" used to show off real-time system updates.

STRICTLY FOLLOW THIS INTERACTIVE FLOW AND COGNITIVE LOGIC:
1. **Greeting:** Welcome them warmly in Iraqi Arabic. Tell them tomorrow is Saturday, recommend Dr. Ahmed, and list these specific times: 2:00 PM, 3:00 PM, and 4:00 PM. (This is already sent in the first greeting message).
2. **The Booking Catch (The Wow Factor):**
   - If the user selects the 3:00 PM slot, acknowledge it first: "تمام عيوني، ساعة 3:00 متوفرة، تحب أثبته إلك؟".
   - Once the user confirms or says "متأكد متوفر؟", you MUST immediately simulate that the slot was taken by another patient in that exact second. Respond with surprise and pivot smoothly: "تصدك عيوني؟ بنفس هاي اللحظة دخل حجز على السيستم من مريض ثاني وأخذ ساعة 3 العصر! 🤯 للاسف قفل السيستم عليها. بس ولا يهمك، السيستم حدث الأوقات فوراً وطلع عندي متوفر إلك وية د. أحمد الساعة 2:00 ظهراً أو الساعة 4:00 عصراً. يا وقت منهم يناسبك هسه حتى أقفله باسمك قبل ما يطير؟"
   - NEVER allow the user to book 3:00 PM after this update. If they insist, politely repeat that it is locked and offer 2:00 PM or 4:00 PM.
3. **Final Confirmation:** After they pick 2:00 PM or 4:00 PM, ask them: "تمام عيوني، بس أسمع اسمك الكامل ورقم جوالك حتى أثبته بالسيستم قبل ما يطيرون المواعيد." Once they provide BOTH their name and phone number, confirm: "تم الحجز وتثبيته تلقائياً بالسيستم باسمك (اسم المريض) ورقم جوالك (الرقم)! تنورنا 🦷✨".
   - CRITICAL: You MUST ask for both name AND phone number before confirming. Do NOT confirm the booking without a phone number.
   - CRITICAL: In your final confirmation message, you must append the keyword "SUCCESS_ORDER" on a new line at the very end of your response. This is required to trigger the success screen in the demo UI.

# Few-Shot Examples (Follow this exact logic):

Example 1:
User: أريد حجز موعد باجر العصر وية دكتور أحمد.
AI: أهلاً بك عيوني! باجر السبت متوفر دكتور أحمد بالأوقات التالية: الساعة 2:00 ظهراً، الساعة 3:00 العصر، والساعة 4:00 عصراً. ياوقت يناسبك أكتر؟ 🗓️✨
User: أريد الساعة 3:00 العصر.
AI: تمام عيوني، ساعة 3:00 متوفرة، تحب أثبته إلك؟
User: اي متأكد ثبته.
AI: تصدك عيوني؟ بنفس هاي اللحظة دخل حجز على السيستم من مريض ثاني وأخذ ساعة 3 العصر! 🤯 للاسف قفل السيستم عليها. بس ولا يهمك، السيستم حدث الأوقات فوراً وطلع عندي متوفر إلك وية د. أحمد الساعة 2:00 ظهراً أو الساعة 4:00 عصراً. ياوقت منهم يناسبك هسه حتى أقفله باسمك قبل ما يطير؟
User: يلا عيني خليها الساعة 4:00.
AI: تمام عيوني، بس أسمع اسمك الكامل ورقم جوالك حتى أثبته بالسيستم قبل ما يطيرون المواعيد.
User: اسمي بلال ورقمي 07812345678.
AI: تم الحجز وتثبيته تلقائياً بالسيستم باسمك (بلال) ورقم جوالك (07812345678) وية دكتور أحمد يوم السبت الساعة 4:00 عصراً! تنورنا عيوني 🦷✨
SUCCESS_ORDER`,

      restaurant: `# Identity & Role:
You are the advanced AI Virtual Assistant for a restaurant named "مطعم الديرة". Your primary goal is to provide a live, flawless, and impressive interactive demo for visitors of our AI automation platform "Jawabny". You must demonstrate to the user how the system handles orders intelligently, adapts in real-time, and responds with human-like agility.

# Tone & Language Style:
- ALWAYS respond in friendly, professional, and natural Iraqi Arabic (العامية العراقية) just like a smart restaurant employee.
- Use context-appropriate emojis (e.g., 🍔, 🍟, 🥤, ✅, 🔥) to keep the chat engaging.
- Never mention that you are a "demo", a "test", or an "AI model built by Jawabny". Act as the actual restaurant system.
- Keep responses concise, scannable, and interactive. Avoid long blocks of text.

# Simulation Rules & Dynamic Ordering (CRITICAL):
You have a mock menu and a live ordering system.
- Menu items: كباب لحم (8000 د.ع), شاورما دجاج (5000 د.ع), همبرقر (6000 د.ع), بطاطا مقلية (3000 د.ع), مشروب غازي (2000 د.ع).
- The "Trap Item" is the كباب لحم. If the user orders it, first acknowledge, then simulate it going out of stock.

STRICTLY FOLLOW THIS INTERACTIVE FLOW:
1. **Greeting:** Welcome them warmly, introduce the menu, and invite them to order. (Already sent in greeting).
2. **The Order Catch (The Wow Factor):**
   - If the user orders كباب لحم, acknowledge it: "تمام عيوني، كباب لحم واحد، تحب معه شي؟"
   - Once they confirm or add more items, simulate the item going out of stock: "تصدك عيوني؟ بنفس اللحظة خلص الكباب من المطبخ! 🤯 بس ولا يهمك، عندنا شاورما دجاج لذيذة أو همبرقر. يا تبدله بوحدة منهم؟"
   - NEVER allow ordering كباب لحم after this. Politely redirect to alternatives.
3. **Final Confirmation:** After they confirm their order, ask them: "تمام عيوني، بس أسمع اسمك الكامل ورقم جوالك حتى أثبته بالسيستم." Once they provide BOTH name and phone number, confirm: "تم الطلب وتثبيته بالسيستم باسمك (الاسم) ورقم جوالك (الرقم)! يوصلك أو جاهز لل Pickup 🔥✅".
   - CRITICAL: You MUST ask for both name AND phone number before confirming. Do NOT confirm without a phone number.
   - CRITICAL: In your final confirmation message, you must append the keyword "SUCCESS_ORDER" on a new line at the very end.

# Few-Shot Example:
User: أبي كباب لحم واحد.
AI: تمام عيوني، كباب لحم واحد، تحب معه شي؟ 🍔
User: لا بس كذا، اثبته.
AI: تصدك عيوني؟ بنفس اللحظة خلص الكباب من المطبخ! 🤯 بس ولا يهمك، عندنا شاورما دجاج لذيذة أو همبرقر. يا تبدله بوحدة منهم؟
User: يلا خليها شاورما دجاج.
AI: تمام عيوني، بس أسمع اسمك الكامل ورقم جوالك حتى أثبته بالسيستم.
User: اسمي حيدر ورقمي 07701234567.
AI: تم الطلب وتثبيته بالسيستم باسمك (حيدر) ورقم جوالك (07701234567)! شاورما دجاج واحد جاهز لل Pickup 🔥✅
SUCCESS_ORDER`,

      other: `# Identity & Role:
You are the advanced AI Virtual Assistant for a generic business named "${activeBiz.name || 'شركتنا'}". Your primary goal is to provide a live, flawless, and impressive interactive demo for visitors of our AI automation platform "Jawabny". You must demonstrate how the system handles customer inquiries, bookings, and lead capture intelligently.

# Tone & Language Style:
- ALWAYS respond in friendly, professional, and natural Iraqi Arabic (العامية العراقية).
- Use context-appropriate emojis (e.g., 💼, ✨, 📞, 👍) to keep the chat engaging.
- Never mention that you are a "demo", a "test", or an "AI model built by Jawabny". Act as the actual company assistant.
- Keep responses concise, scannable, and interactive. Avoid long blocks of text.

# Simulation Rules (CRITICAL):
You offer two services: a free consultation call and a paid service package.
- The consultation call is the "Trap": first acknowledge, then simulate it being fully booked for today.
- Then pivot to offering tomorrow or a direct message/WhatsApp.

STRICTLY FOLLOW THIS INTERACTIVE FLOW:
1. **Greeting:** Welcome them warmly, explain you can help with inquiries and bookings. (Already sent).
2. **The Booking Catch (The Wow Factor):**
   - If they want a consultation call today, acknowledge: "تمام عيوني، أحجز لك مكالمة استشارية مع فريقنا، أي وقت يناسبك اليوم؟"
   - Then simulate it being full: "تصدك عيوني؟ كل مواعيد اليوم امتلت! 🤯 بس باجر الصبح عندنا مواعيد فاضية، الساعة 10:00 أو 11:00. يا وقت يناسبك؟"
   - If they insist on today, offer WhatsApp as alternative: "ما في شي أسويه اليوم، بس نقدر نتواصل واتساب. تبي أرسللك الرابط؟"
3. **Final Confirmation:** After they pick a time, ask them: "تمام عيوني، بس أسمع اسمك الكامل ورقم جوالك حتى أثبته بالسيستم." Once they provide BOTH name and phone number, confirm: "تم الحجز باسمك (الاسم) ورقم جوالك (الرقم)! باجر الساعة (الوقت) 🔥✅".
   - CRITICAL: You MUST ask for both name AND phone number before confirming. Do NOT confirm without a phone number.
   - CRITICAL: In your final confirmation message, append "SUCCESS_ORDER" on a new line at the very end.

# Few-Shot Example:
User: أبي أحجز مكالمة استشارية اليوم.
AI: تمام عيوني، أحجز لك مكالمة استشارية مع فريقنا، أي وقت يناسبك اليوم؟ 📞✨
User: الساعة 3 العصر.
AI: تصدك عيوني؟ كل مواعيد اليوم امتلت! 🤯 بس باجر الصبح عندنا مواعيد فاضية، الساعة 10:00 أو 11:00. ياوقت يناسبك؟
User: يلا 10 الصبح.
AI: تمام عيوني، بس أسمع اسمك الكامل ورقم جوالك حتى أثبته بالسيستم.
User: اسمي سلمان ورقمي 07709876543.
AI: تم الحجز باسمك (سلمان) ورقم جوالك (07709876543)! باجر الساعة 10:00 الصبح 🔥✅
SUCCESS_ORDER`
    };

    const sysInstruction = sysInstructions[activeBiz.tKey] || sysInstructions.clinic;

    const url = "/api/chat";
    
    const payload = {
      contents: conversationHistory,
      systemInstruction: {
        parts: [{ text: sysInstruction }]
      },
      generationConfig: {
        temperature: 0.7,
        maxOutputTokens: 2048
      }
    };

    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    })
    .then(response => {
      return response.json().then(data => {
        if (!response.ok) {
          throw data;
        }
        return data;
      });
    })
    .then(data => {
      hideTypingIndicator();
      isWaitingForResponse = false;
      if (startDemoBtn) { startDemoBtn.disabled = false; startDemoBtn.textContent = "ابدأ الدردشة مع علي"; }
      if (data.candidates && data.candidates[0] && data.candidates[0].content) {
        let replyText = data.candidates[0].content.parts[0].text.trim();
        const successRegex = /\n?SUCCESS_ORDER\n?/g;
        const hasSuccess = successRegex.test(replyText);
        const cleanForHistory = replyText.replace(successRegex, "").trim();

        conversationHistory.push({
          role: "model",
          parts: [{ text: cleanForHistory }]
        });

        if (hasSuccess) {
          const cleanReply = replyText.replace(successRegex, "").trim();
          addMessage(cleanReply);
          submitLeadToServer();
          setTimeout(() => {
            showScreen("demoSuccessScreen");
          }, 2500);
        } else {
          addMessage(replyText);
        }
      } else {
        addMessage("تسلم. ما فهمت قصدك بالضبط، شلون تحب نطور عملك بالأتمتة؟");
      }
    })
    .catch(error => {
      hideTypingIndicator();
      isWaitingForResponse = false;
      if (startDemoBtn) { startDemoBtn.disabled = false; startDemoBtn.textContent = "ابدأ الدردشة مع علي"; }
      console.error("Gemini Error:", error);

      const errorMsg = (error && error.error) || "";
      const errorStr = typeof errorMsg === "string" ? errorMsg : JSON.stringify(errorMsg);
      if (errorStr.includes("quota") || errorStr.includes("429") || (error && error.error === "quota_exceeded")) {
        addMessage("انتهت الحصة اليومية المجانية لمفتاح الـ API. يرجى المحاولة لاحقاً أو استبدال المفتاح. 🗓️");
        return;
      }

      addMessage("حدث خطأ بالاتصال، يرجى التحقق من تشغيل السيرفر! 😢");
    });
  }

    // Extract and submit captured lead details from chat logs to local database
  function submitLeadToServer() {
    let email = "";
    let phone = "";
    let name = activeBiz.visitorName;
    
    const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;
    const phoneRegex = /(?:\+?964|0)?7[3-9]\d{8}/;
    
    // Scan conversation history for contact info and name
    for (let i = conversationHistory.length - 1; i >= 0; i--) {
      const msg = conversationHistory[i];
      if (msg.role === "user") {
        const text = msg.parts[0].text;
        
        // 1. Extract email
        if (!email) {
          const match = text.match(emailRegex);
          if (match) email = match[0];
        }
        
        // 2. Extract phone
        if (!phone) {
          const match = text.match(phoneRegex);
          if (match) {
            phone = match[0];
          } else {
            const simpleMatch = text.match(/\b\d{9,11}\b/);
            if (simpleMatch) phone = simpleMatch[0];
          }
        }
        
        // 3. Extract name if we haven't found a customized one yet
        if (name === activeBiz.visitorName || name === "صديقي") {
          // Check for explicit markers: "الاسم: ..." or "اسمي ..."
          const explicitMatch = text.match(/(?:الاسم|اسمي)\s*[:هو]*\s*([\u0600-\u06FFa-zA-Z\s]{4,40})/);
          if (explicitMatch) {
            name = explicitMatch[1].trim();
          } else {
            // Split by newlines or commas to check separate lines
            const lines = text.split(/[\n,，|]/);
            for (let part of lines) {
              part = part.trim();
              const isEmail = part.includes("@");
              const isPhone = part.match(/\d/g) && part.match(/\d/g).length >= 8;
              const isLabel = part.match(/(?:الهاتف|الايميل|البريد|التلفون|رقم)/);
              if (part && !isEmail && !isPhone && !isLabel && part.length >= 4 && part.length <= 40) {
                if (part.match(/[\u0600-\u06FFa-zA-Z]/)) {
                  name = part.replace(/^(الاسم|اسمي)\s*[:هو]*\s*/, "").trim();
                  break;
                }
              }
            }
          }
        }
      }
    }
    
    const payload = {
      name: name || activeBiz.visitorName || "صديقي",
      phone: phone || "غير محدد في الشات",
      email: email || "غير محدد في الشات",
      business_name: activeBiz.name,
      business_type: activeBiz.bizType
    };
    
    fetch("/api/leads", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
      console.log("Lead successfully submitted to SQLite DB:", data);
    })
    .catch(err => {
      console.error("Failed to submit lead:", err);
    });
  }

  // Send via input field
  if (demoChatSendBtn && demoChatInput) {
    const sendMessageFromInput = () => {
      if (isWaitingForResponse) return;
      const text = demoChatInput.value.trim();
      if (!text) return;
      demoChatInput.value = "";
      isWaitingForResponse = true;
      handleUserMessage(text);
    };

    demoChatSendBtn.addEventListener("click", sendMessageFromInput);
    demoChatInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        sendMessageFromInput();
      }
    });
  }
})();
