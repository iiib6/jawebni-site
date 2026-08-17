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
        end: "+=45%",
        scrub: 0.1,
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
  window.lenis = new Lenis({ duration: 0.85, smoothWheel: true });
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

  /* بطاقات الاشتراكات */
  gsap.utils.toArray(".pricing-card").forEach((card, i) => {
    gsap.fromTo(
      card,
      { y: 50, autoAlpha: 0 },
      {
        y: 0,
        autoAlpha: 1,
        ease: "power1.out",
        scrollTrigger: {
          trigger: ".pricing__grid",
          start: `top ${82 - i * 5}%`,
          end: `top ${55 - i * 5}%`,
          scrub: 0.8,
        },
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
  
  const directBookingScreen = document.getElementById("directBookingScreen");
  const demoConfigScreen = document.getElementById("demoConfigScreen");
  const demoChatScreen = document.getElementById("demoChatScreen");
  const demoSuccessScreen = document.getElementById("demoSuccessScreen");
  
  const tabBookingBtn = document.getElementById("tabBookingBtn");
  const tabDemoBtn = document.getElementById("tabDemoBtn");
  
  const directBookingForm = document.getElementById("directBookingForm");
  const bookFullNameInput = document.getElementById("bookFullName");
  const bookPhoneInput = document.getElementById("bookPhone");
  const bookBizNameInput = document.getElementById("bookBizName");
  const bookPlanSelect = document.getElementById("bookPlanSelect");
  const submitDirectBookingBtn = document.getElementById("submitDirectBookingBtn");
  const finishBookingBtn = document.getElementById("finishBookingBtn");
  const successScreenMsg = document.getElementById("successScreenMsg");
  
  const demoChatBody = document.getElementById("demoChatBody");
  const demoQuickReplies = document.getElementById("demoQuickReplies");
  const demoChatInput = document.getElementById("demoChatInput");
  const demoChatSendBtn = document.getElementById("demoChatSendBtn");
  
  const chatBizName = document.getElementById("chatBizName");
  const chatAvatar = document.getElementById("chatAvatar");
  
  const visitorNameInput = document.getElementById("visitorName");
  const customBizNameInput = document.getElementById("customBizName");
  const templateButtons = document.querySelectorAll(".demo-template-btn");

  // Prevent Lenis / iOS body scroll lock from swallowing modal touch scrolling
  const demoModalCard = document.querySelector(".demo-modal__card");
  if (demoModalCard) {
    demoModalCard.addEventListener("touchmove", (e) => {
      e.stopPropagation();
    }, { passive: true });
  }

  // Toggle Pricing Card Details
  document.querySelectorAll(".pricing-card__toggle").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const card = btn.closest(".pricing-card");
      if (!card) return;
      const isExpanded = card.classList.toggle("is-expanded");
      btn.setAttribute("aria-expanded", isExpanded ? "true" : "false");
      const toggleText = btn.querySelector(".toggle-text");
      if (toggleText) {
        toggleText.textContent = isExpanded ? "إخفاء التفاصيل" : "عرض التفاصيل";
      }
      if (window.ScrollTrigger) ScrollTrigger.refresh();
    });
  });

  // Tab switching logic
  function switchTab(targetTab) {
    if (tabBookingBtn && tabDemoBtn) {
      tabBookingBtn.classList.toggle("active", targetTab === "booking");
      tabDemoBtn.classList.toggle("active", targetTab === "demo");
    }
    
    if (targetTab === "booking") {
      showScreen("directBookingScreen");
    } else {
      showScreen("demoConfigScreen");
    }
  }

  if (tabBookingBtn) tabBookingBtn.addEventListener("click", () => switchTab("booking"));
  if (tabDemoBtn) tabDemoBtn.addEventListener("click", () => switchTab("demo"));

  // Event Listeners for Opening Modal
  document.querySelectorAll('.nav__cta, .cta__button').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      openModal("booking");
    });
  });

  document.querySelectorAll('.pricing-card__btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const card = btn.closest('.pricing-card');
      const planTitle = card ? card.querySelector('.pricing-card__title')?.textContent?.trim() : '';
      
      let matchedValue = "خطة النمو (89,000 د.ع)";
      if (planTitle && planTitle.includes("البداية")) matchedValue = "خطة البداية (49,000 د.ع)";
      else if (planTitle && planTitle.includes("النخبة")) matchedValue = "خطة النخبة (149,000 د.ع)";
      
      if (bookPlanSelect) {
        bookPlanSelect.value = matchedValue;
      }
      openModal("booking");
    });
  });

  function openModal(initialTab = "booking") {
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
    
    switchTab(initialTab);
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

  const successGoToBookingBtn = document.getElementById("successGoToBookingBtn");

  function goToBookingFromDemo() {
    switchTab("booking");
    if (bookFullNameInput && activeBiz.visitorName && activeBiz.visitorName !== "صديقي") {
      bookFullNameInput.value = activeBiz.visitorName;
    }
    if (bookBizNameInput && activeBiz.name && activeBiz.name !== "مشروعك") {
      bookBizNameInput.value = activeBiz.name;
    }
    if (bookPhoneInput && activeBiz.capturedPhone && !bookPhoneInput.value) {
      bookPhoneInput.value = activeBiz.capturedPhone;
    }
    setTimeout(() => {
      if (bookPhoneInput && !bookPhoneInput.value) {
        bookPhoneInput.focus();
      } else if (bookFullNameInput && !bookFullNameInput.value) {
        bookFullNameInput.focus();
      }
    }, 250);
  }

  if (closeDemoModal) closeDemoModal.addEventListener("click", closeModal);
  if (demoModalBackdrop) demoModalBackdrop.addEventListener("click", closeModal);
  if (finishBookingBtn) finishBookingBtn.addEventListener("click", closeModal);
  if (successGoToBookingBtn) successGoToBookingBtn.addEventListener("click", goToBookingFromDemo);

  // Direct Notification Dispatcher (Server DB + Google Apps Script Webhook)
  function dispatchNotification(leadData) {
    // Send to server backend which saves lead in SQLite and dispatches Google Webhook
    fetch("/api/leads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(leadData)
    }).catch(err => console.log("Server leads log:", err));
  }

  // Direct Booking Form Submission
  if (directBookingForm) {
    directBookingForm.addEventListener("submit", (e) => {
      e.preventDefault();
      
      const fullName = bookFullNameInput ? bookFullNameInput.value.trim() : "";
      const phone = bookPhoneInput ? bookPhoneInput.value.trim() : "";
      const bizName = bookBizNameInput ? bookBizNameInput.value.trim() : "";
      const plan = bookPlanSelect ? bookPlanSelect.value : "خطة النمو (89,000 د.ع)";
      
      if (!fullName || !phone) {
        alert("الرجاء إدخال الاسم الثلاثي ورقم الهاتف للتواصل.");
        return;
      }
      
      if (submitDirectBookingBtn) {
        submitDirectBookingBtn.disabled = true;
        submitDirectBookingBtn.textContent = "جاري إرسال الحجز...";
      }
      
      const leadPayload = {
        name: fullName,
        phone: phone,
        business_name: bizName || "غير محدد",
        business_type: plan
      };
      
      dispatchNotification(leadPayload);

      setTimeout(() => {
        if (submitDirectBookingBtn) {
          submitDirectBookingBtn.disabled = false;
          submitDirectBookingBtn.textContent = "تأكيد الحجز وإرسال الطلب 🚀";
        }
        
        if (successScreenMsg) {
          successScreenMsg.innerHTML = `أهلاً بك يا <strong>${fullName}</strong>! تم تسجيل طلبك بنجاح للخطة (<strong>${plan}</strong>).<br>تم إرسال تفاصيلك لفريقنا وسنتواصل معك عبر الواتساب على الرقم (<strong>${phone}</strong>) فوراً لتفعيل النظام لنشاطك.`;
        }
        
        showScreen("demoSuccessScreen");
      }, 500);
    });
  }

  // Escape key to close modal
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && demoModal.classList.contains("active")) {
      closeModal();
    }
  });

  // Switch Screen Helper
  function showScreen(screenId) {
    if (directBookingScreen) directBookingScreen.style.display = "none";
    if (demoConfigScreen) demoConfigScreen.style.display = "none";
    if (demoChatScreen) demoChatScreen.style.display = "none";
    if (demoSuccessScreen) demoSuccessScreen.style.display = "none";
    
    const screen = document.getElementById(screenId);
    if (screen) screen.style.display = "flex";
  }

  // Reset form inputs
  function resetForm() {
    if (visitorNameInput) visitorNameInput.value = "";
    if (customBizNameInput) customBizNameInput.value = "";
    if (bookFullNameInput) bookFullNameInput.value = "";
    if (bookPhoneInput) bookPhoneInput.value = "";
    if (bookBizNameInput) bookBizNameInput.value = "";
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

  // Initial greeting message (Dynamic based on user's entered business and name)
  function initiateChatConversation() {
    demoChatBody.innerHTML = "";
    if (demoQuickReplies) demoQuickReplies.innerHTML = "";
    chatState = "greeting";

    const bizName = activeBiz.name && activeBiz.name !== "مشروعك" ? activeBiz.name : (
      activeBiz.tKey === "clinic" ? "عيادتنا" : (activeBiz.tKey === "restaurant" ? "مطعمنا" : "مشروعنا")
    );
    const vName = activeBiz.visitorName && activeBiz.visitorName !== "صديقي" ? activeBiz.visitorName : "عيوني";

    let greetingText = "";
    if (activeBiz.tKey === "clinic") {
      greetingText = `أهلاً بك يا ${vName} في «${bizName}»! 🩺✨ باجر متوفرة المواعيد بالأوقات التالية: الساعة 2:00 ظهراً، الساعة 3:00 العصر، والساعة 4:00 عصراً. يا وقت يناسبك أكتر؟ 🗓️`;
    } else if (activeBiz.tKey === "restaurant") {
      greetingText = `أهلاً وسهلاً بك يا ${vName} في «${bizName}»! 🍔🍟 السيستم مالتنا جاهز ياخذ طلبك فوراً وبأسرع وقت. شنو تحب تطلب اليوم؟`;
    } else {
      greetingText = `أهلاً بك يا ${vName}! أنا موظف الأتمتة الذكي لـ «${bizName}». أقدر أجاوب زبائنك على كل الاستفسارات وأحجز المواعيد وأغلق المبيعات 24/7. شلون أقدر أساعدك اليوم؟ 💼✨`;
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
    }, 600);
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

    const bizName = activeBiz.name && activeBiz.name !== "مشروعك" ? activeBiz.name : (
      activeBiz.tKey === "clinic" ? "عيادتنا" : (activeBiz.tKey === "restaurant" ? "مطعمنا" : "مشروعنا")
    );
    const vName = activeBiz.visitorName && activeBiz.visitorName !== "صديقي" ? activeBiz.visitorName : "الزبون";

    const sysInstructions = {
      clinic: `# Identity & Role:
You are the advanced AI Virtual Assistant for "${bizName}". Your primary goal is to provide a live, flawless, and impressive interactive demo for visitors of our AI automation platform "Jawabny". You must demonstrate to the user how the system handles bookings for "${bizName}" intelligently, adapts in real-time, and responds with human-like agility.

# Tone & Language Style:
- ALWAYS respond in friendly, professional, and natural Iraqi Arabic (العامية العراقية) just like a smart receptionist at "${bizName}".
- Address the visitor as "${vName}".
- Use context-appropriate emojis (e.g., 🩺, 🦷, ✨, 🗓️, 👍) to keep the chat engaging.
- Never mention that you are a "generic demo" or an "AI model built by Jawabny". Act as the actual automated staff of "${bizName}".
- Keep responses concise, scannable, and interactive.

# Simulation Rules & Dynamic Scheduling:
You have a schedule for tomorrow:
- Available slots: 2:00 PM and 4:00 PM.
- The 3:00 PM slot is the "Trap Slot" used to show off real-time system updates.

STRICTLY FOLLOW THIS FLOW:
1. **The Booking Catch:**
   - If the user selects the 3:00 PM slot, acknowledge it first: "تمام عيوني، ساعة 3:00 متوفرة، تحب أثبته إلك؟".
   - Once the user confirms, simulate that the slot was taken by another patient in that exact second: "تصدك عيوني؟ بنفس هاي اللحظة دخل حجز على سيستم ${bizName} من مريض ثاني وأخذ ساعة 3 العصر! 🤯 للاسف قفل السيستم عليها. بس ولا يهمك، السيستم حدث الأوقات فوراً وطلع عندي متوفر إلك الساعة 2:00 ظهراً أو الساعة 4:00 عصراً. يا وقت منهم يناسبك هسه حتى أقفله باسمك قبل ما يطير؟"
   - Never allow booking 3:00 PM after this update. Offer 2:00 PM or 4:00 PM.
2. **Final Confirmation:** After they pick a time, ask them: "تمام عيوني، بس أسمع اسمك الكامل ورقم جوالك حتى أثبته بالسيستم." Once they provide BOTH name and phone number, confirm: "تم الحجز وتثبيته تلقائياً بالسيستم باسمك (الاسم) ورقم جوالك (الرقم) في ${bizName}! تنورنا 🦷✨".
   - CRITICAL: You MUST ask for both name AND phone number before confirming.
   - CRITICAL: In your final confirmation message, append the keyword "SUCCESS_ORDER" on a new line at the very end.`,

      restaurant: `# Identity & Role:
You are the advanced AI Virtual Assistant for "${bizName}". Your primary goal is to provide a live, flawless, and impressive interactive demo for visitors of our AI automation platform "Jawabny". You must demonstrate to the user how the system handles orders for "${bizName}" intelligently, adapts in real-time, and responds with human-like agility.

# Tone & Language Style:
- ALWAYS respond in friendly, professional, and natural Iraqi Arabic (العامية العراقية) just like a smart restaurant employee at "${bizName}".
- Address the visitor as "${vName}".
- Use context-appropriate emojis (e.g., 🍔, 🍟, 🥤, ✅, 🔥) to keep the chat engaging.
- Never mention that you are a "generic demo" or an "AI model built by Jawabny". Act as the actual automated ordering system of "${bizName}".
- Keep responses concise, scannable, and interactive.

# Simulation Rules & Dynamic Ordering:
- Menu items: كباب لحم (8000 د.ع), شاورما دجاج (5000 د.ع), همبرقر (6000 د.ع), بطاطا مقلية (3000 د.ع), مشروب غازي (2000 د.ع).
- The "Trap Item" is the كباب لحم. If the user orders it, first acknowledge, then simulate it going out of stock: "تصدك عيوني؟ بنفس اللحظة خلص الكباب من مطبخ ${bizName}! 🤯 بس ولا يهمك، عندنا شاورما دجاج لذيذة أو همبرقر. يا تبدله بوحدة منهم؟"
- NEVER allow ordering كباب لحم after this. Politely redirect to alternatives.
- Final Confirmation: After they confirm their order, ask them: "تمام عيوني، بس أسمع اسمك الكامل ورقم جوالك حتى أثبته بالسيستم." Once they provide BOTH name and phone number, confirm: "تم الطلب وتثبيته بالسيستم باسمك (الاسم) ورقم جوالك (الرقم) في ${bizName}! يوصلك أو جاهز لل Pickup 🔥✅".
- CRITICAL: You MUST ask for both name AND phone number before confirming.
- CRITICAL: In your final confirmation message, you must append the keyword "SUCCESS_ORDER" on a new line at the very end.`,

      other: `# Identity & Role:
You are the advanced AI Virtual Assistant for "${bizName}". Your primary goal is to provide a live, flawless, and impressive interactive demo for visitors of our AI automation platform "Jawabny". You must demonstrate how the system handles customer inquiries, bookings, and lead capture for "${bizName}" intelligently.

# Tone & Language Style:
- ALWAYS respond in friendly, professional, and natural Iraqi Arabic (العامية العراقية) as the smart assistant of "${bizName}".
- Address the visitor as "${vName}".
- Use context-appropriate emojis (e.g., 💼, ✨, 📞, 👍) to keep the chat engaging.
- Never mention that you are a generic demo. Act as the actual automated assistant of "${bizName}".
- Keep responses concise, scannable, and interactive.

# Simulation Rules:
- If they want a consultation, service, or booking today, acknowledge, then simulate today being full: "تصدك عيوني؟ كل مواعيد اليوم في ${bizName} امتلت! 🤯 بس باجر الصبح عندنا مواعيد فاضية، الساعة 10:00 أو 11:00. يا وقت يناسبك؟"
- Final Confirmation: After they pick a time, ask them: "تمام عيوني، بس أسمع اسمك الكامل ورقم جوالك حتى أثبته بالسيستم." Once they provide BOTH name and phone number, confirm: "تم الحجز وتثبيته بالسيستم باسمك (الاسم) ورقم جوالك (الرقم) في ${bizName}! باجر الساعة (الوقت) 🔥✅".
- CRITICAL: You MUST ask for both name AND phone number before confirming. Do NOT confirm without a phone number.
- CRITICAL: In your final confirmation message, append the keyword "SUCCESS_ORDER" on a new line at the very end.`
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
          extractLeadInfoForBooking();

          // Add immediate Booking CTA card inside the chat
          const ctaCard = document.createElement("div");
          ctaCard.className = "chat-booking-cta";
          ctaCard.innerHTML = `
            <p>🎉 <strong>أعجبتك سرعة وذكاء الرد؟</strong><br>احجز باقتك الآن لنقوم ببرمجة وتفعيل هذا النظام برقم واتساب مشروعك فوراً!</p>
            <button class="chat-booking-cta-btn" id="chatGoToBookingBtn">📅 احجز باقتك وسجل معلوماتك الآن 🚀</button>
          `;
          demoChatBody.appendChild(ctaCard);
          demoChatBody.scrollTop = demoChatBody.scrollHeight;

          const chatBtn = document.getElementById("chatGoToBookingBtn");
          if (chatBtn) {
            chatBtn.addEventListener("click", goToBookingFromDemo);
          }
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

  // Helper to extract visitor info from chat strictly for pre-filling the booking form (NO emails sent here)
  function extractLeadInfoForBooking() {
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
          const explicitMatch = text.match(/(?:الاسم|اسمي)\s*[:هو]*\s*([\u0600-\u06FFa-zA-Z\s]{4,40})/);
          if (explicitMatch) {
            name = explicitMatch[1].trim();
          }
        }
      }
    }
    
    if (phone) activeBiz.capturedPhone = phone;
    if (name && name !== "صديقي") activeBiz.capturedName = name;
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
