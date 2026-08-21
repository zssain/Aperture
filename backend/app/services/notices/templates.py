"""Deterministic notice copy, English + Hindi.

These templates are the PERMANENT fallback: Prompt 18 may add an optional LLM rendering on top,
but it must be validated against these and can never replace them. Copy rules enforced here:
state the decision and terms; give up to three reasons in plain language; for recourse, state the
action, that it does NOT ensure approval, and the expiry. A notice NEVER quotes a threshold or a
policy internal - the reason phrases are qualitative and carry no numbers.
"""

NOTICE_TEMPLATE_VERSION = "notice-v1"
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "hi")
DEFAULT_LANGUAGE = "en"


def outcome_class(outcome: str) -> str:
    if outcome.startswith("APPROVE"):
        return "approved"
    if outcome.startswith("DECLINE"):
        return "declined"
    return "review"


# --------------------------------------------------------------------------- #
# Decision notice copy.
# --------------------------------------------------------------------------- #
DECISION_COPY: dict[str, dict[str, str]] = {
    "en": {
        "subject": "Your credit application decision",
        "approved": "Your application has been approved.",
        "declined": "We are unable to approve your application at this time.",
        "review": "Your application is being reviewed by our team.",
        "terms": "Approved amount: ₹{amount}. Term: {tenor} months. Interest rate: {rate}% per year.",
        "reasons_heading": "Key factors in this decision:",
        "closing": "If you have any questions, please contact our support team.",
    },
    "hi": {
        "subject": "आपके ऋण आवेदन का निर्णय",
        "approved": "आपका आवेदन स्वीकृत कर दिया गया है।",
        "declined": "हम इस समय आपके आवेदन को स्वीकृत करने में असमर्थ हैं।",
        "review": "आपके आवेदन की हमारी टीम द्वारा समीक्षा की जा रही है।",
        "terms": "स्वीकृत राशि: ₹{amount}. अवधि: {tenor} महीने. ब्याज दर: {rate}% प्रति वर्ष.",
        "reasons_heading": "इस निर्णय के मुख्य कारक:",
        "closing": "किसी भी प्रश्न के लिए कृपया हमारी सहायता टीम से संपर्क करें।",
    },
}

# Qualitative reason phrases - no numbers, no thresholds, no policy internals.
REASON_COPY: dict[str, dict[str, str]] = {
    "en": {
        "GATE_DECLINE_RISK": "Your recent financial activity did not meet our current requirements.",
        "GATE_DECLINE_AFFORDABILITY": "The requested amount may be difficult to repay alongside your existing commitments.",
        "GATE_REVIEW_EVIDENCE": "We need a little more information to complete your assessment.",
        "GATE_REVIEW_FRAUD": "Your application needs an additional verification check.",
        "GATE_FRAUD_REVIEW": "Your application needs an additional verification check.",
        "GATE_APPROVE": "Your financial history supported this decision.",
        "COVERAGE_GAP": "Connecting more of your financial records would strengthen your application.",
        "AFFORDABILITY_DSR": "Your existing repayments take up a large share of your income.",
        "AFFORDABILITY_MAX_PRINCIPAL": "A smaller amount may be more manageable for your budget.",
        "RISK_CONTRIBUTOR": "Your recent account activity influenced this assessment.",
        "MANDATORY_REVIEW": "A manual review was required for an amount of this size.",
        "EXPLORATION_COHORT": "You were offered a starter facility to help build your history.",
    },
    "hi": {
        "GATE_DECLINE_RISK": "आपकी हाल की वित्तीय गतिविधि हमारी वर्तमान आवश्यकताओं को पूरा नहीं करती।",
        "GATE_DECLINE_AFFORDABILITY": "अनुरोधित राशि आपकी मौजूदा प्रतिबद्धताओं के साथ चुकाना कठिन हो सकता है।",
        "GATE_REVIEW_EVIDENCE": "आपके मूल्यांकन को पूरा करने के लिए हमें थोड़ी और जानकारी चाहिए।",
        "GATE_REVIEW_FRAUD": "आपके आवेदन को एक अतिरिक्त सत्यापन जाँच की आवश्यकता है।",
        "GATE_FRAUD_REVIEW": "आपके आवेदन को एक अतिरिक्त सत्यापन जाँच की आवश्यकता है।",
        "GATE_APPROVE": "आपके वित्तीय इतिहास ने इस निर्णय का समर्थन किया।",
        "COVERAGE_GAP": "अधिक वित्तीय रिकॉर्ड जोड़ने से आपका आवेदन मज़बूत होगा।",
        "AFFORDABILITY_DSR": "आपकी मौजूदा किश्तें आपकी आय का बड़ा हिस्सा लेती हैं।",
        "AFFORDABILITY_MAX_PRINCIPAL": "एक छोटी राशि आपके बजट के लिए अधिक सुविधाजनक हो सकती है।",
        "RISK_CONTRIBUTOR": "आपकी हाल की खाता गतिविधि ने इस मूल्यांकन को प्रभावित किया।",
        "MANDATORY_REVIEW": "इस आकार की राशि के लिए मैन्युअल समीक्षा आवश्यक थी।",
        "EXPLORATION_COHORT": "आपको अपना इतिहास बनाने में मदद के लिए एक स्टार्टर सुविधा दी गई।",
    },
}

GENERIC_REASON: dict[str, str] = {
    "en": "This factor was considered in the outcome.",
    "hi": "इस कारक को परिणाम में ध्यान में रखा गया।",
}


# --------------------------------------------------------------------------- #
# Recourse notice copy.
# --------------------------------------------------------------------------- #
RECOURSE_COPY: dict[str, dict[str, str]] = {
    "en": {
        "subject": "How you can strengthen your application",
        "intro": "You may be able to improve the outcome by taking the action below.",
        "action_line": "What to do: {action}",
        # NB: never promissory. This says approval is not ensured.
        "no_guarantee": "Completing this does not ensure approval; your application will be assessed again.",
        "expiry": "Please complete this by {date}.",
        "none": "There is currently no additional step that would change the outcome.",
    },
    "hi": {
        "subject": "आप अपना आवेदन कैसे मज़बूत कर सकते हैं",
        "intro": "नीचे दी गई कार्रवाई करके आप परिणाम बेहतर कर सकते हैं।",
        "action_line": "क्या करें: {action}",
        "no_guarantee": "इसे पूरा करने से स्वीकृति सुनिश्चित नहीं होती; आपके आवेदन का फिर से मूल्यांकन किया जाएगा।",
        "expiry": "कृपया इसे {date} तक पूरा करें।",
        "none": "फिलहाल ऐसा कोई अतिरिक्त कदम नहीं है जो परिणाम बदल दे।",
    },
}

# Plain-language names for recourse levers (no policy internals).
LEVER_ACTIONS: dict[str, dict[str, str]] = {
    "en": {
        "ADD_SOURCE": "Connect an additional financial account or document.",
        "EXTEND_HISTORY": "Provide a longer history of your account activity.",
        "REDUCE_AMOUNT": "Apply again for a smaller amount.",
        "ACCEPT_STARTER": "Accept a smaller starter facility to begin building your history.",
    },
    "hi": {
        "ADD_SOURCE": "एक अतिरिक्त वित्तीय खाता या दस्तावेज़ जोड़ें।",
        "EXTEND_HISTORY": "अपनी खाता गतिविधि का लंबा इतिहास प्रदान करें।",
        "REDUCE_AMOUNT": "छोटी राशि के लिए फिर से आवेदन करें।",
        "ACCEPT_STARTER": "इतिहास बनाना शुरू करने के लिए एक छोटी स्टार्टर सुविधा स्वीकार करें।",
    },
}


def reason_phrase(code: str, language: str) -> str:
    lang = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    table = REASON_COPY[lang]
    if code in table:
        return table[code]
    if code.startswith("GATE_APPROVE"):
        return table["GATE_APPROVE"]
    return GENERIC_REASON[lang]


def lever_action(lever: str, language: str) -> str:
    lang = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    return LEVER_ACTIONS[lang].get(lever, LEVER_ACTIONS[lang]["ADD_SOURCE"])
