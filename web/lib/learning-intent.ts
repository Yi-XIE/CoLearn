const LIGHT_CHAT_PATTERNS = [
  /^(hi|hello|hey|yo|hiya|howdy|sup|good morning|good afternoon|good evening|hello there|hey there)[\s!,.?~]*$/i,
  /^(浣犲ソ|鎮ㄥソ|鍡▅鍝堝柦|鏅氫笂濂絴鏃╀笂濂絴涓嬪崍濂絴鍦ㄥ悧|鍦ㄥ槢|鏈変汉鍚梶鏈変汉鍦ㄥ悧)[\s!,.?~锛屻€傦紒锛燂綖]*$/i,
];

const LEARNING_HINT_PATTERNS = [
  /\?/,
  /\b(learn|study|understand|explain|practice|review|solve|question|topic|goal|homework|exam|why|how)\b/i,
  /(瀛︿範|棰樼洰|闂|璁茶В|瑙ｉ噴|缁冧範|澶嶄範|鐭ヨ瘑鐐箌鐩爣|浣滀笟|鑰冭瘯|涓轰粈涔坾鎬庝箞|濡備綍)/,
];

export function shouldEnterLearningMode(userMessage: string): boolean {
  const text = String(userMessage || "").trim();
  if (!text) return false;
  if (LIGHT_CHAT_PATTERNS.some((pattern) => pattern.test(text))) return false;
  if (text.length >= 40) return true;
  return LEARNING_HINT_PATTERNS.some((pattern) => pattern.test(text));
}
