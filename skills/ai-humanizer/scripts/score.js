#!/usr/bin/env node
/**
 * score.js — model-agnostic AI-writing-tell scorer.
 *
 * Emits a deterministic 0-100 AI-likeness score for prose read from stdin
 * (or a file arg). Same bytes in -> same number out, on any machine, with no
 * network and no dependencies. The number is a CHECK THAT CAN FAIL: run it on a
 * draft, de-slop, run it again — a lower AFTER proves the pass instead of
 * claiming it. That before/after delta is the evidence.
 *
 * Three signals, blended: pattern density (24 detectors + a tiered vocabulary),
 * category breadth, and statistical uniformity (burstiness, sentence-length
 * variation, type-token ratio, trigram repetition). Vendored and distilled from
 * the Wikipedia:Signs-of-AI-writing corpus and public stylometric research
 * (Copyleaks arXiv:2503.01659, StyloAI). No vendor/model names are hardcoded —
 * the tells are shared across model families.
 *
 * Usage:
 *   node score.js < draft.md        # prints the score, e.g. "72"
 *   node score.js draft.md          # same, from a file
 *   node score.js --json < draft.md # full breakdown as JSON
 */

'use strict';

// ─── Vocabulary ──────────────────────────────────────────

const TIER_1 = [
  'delve','delving','delved','delves','tapestry','vibrant','crucial','comprehensive',
  'intricate','intricacies','pivotal','testament','landscape','bustling','nestled','realm',
  'meticulous','meticulously','complexities','embark','embarking','embarked','robust',
  'showcasing','showcase','showcased','showcases','underscores','underscoring','underscored',
  'fostering','foster','fostered','fosters','seamless','seamlessly','groundbreaking','renowned',
  'synergy','synergies','leverage','leveraging','leveraged','garner','garnered','garnering',
  'interplay','enduring','enhance','enhanced','enhancing','enhancement','tapestry','testament',
  'additionally','daunting','ever-evolving','game changer','game-changing','game-changer',
  'underscore',
];

const TIER_2 = [
  'furthermore','moreover','notably','consequently','subsequently','accordingly','nonetheless',
  'henceforth','indeed','specifically','essentially','ultimately','arguably','fundamentally',
  'inherently','profoundly','encompassing','encompasses','encompassed','endeavour','endeavor',
  'endeavoring','elevate','elevated','elevating','alleviate','alleviating','streamline',
  'streamlined','streamlining','harness','harnessing','harnessed','unleash','unleashing',
  'unleashed','revolutionize','revolutionizing','revolutionized','transformative','transformation',
  'paramount','multifaceted','spearhead','spearheading','spearheaded','bolster','bolstering',
  'bolstered','catalyze','catalyst','catalyzed','cornerstone','reimagine','reimagining',
  'reimagined','empower','empowering','empowerment','empowered','navigate','navigating',
  'navigated','poised','myriad','nuanced','nuance','nuances','paradigm','paradigms',
  'paradigm-shifting','holistic','holistically','utilize','utilizing','utilization','utilized',
  'facilitate','facilitated','facilitating','facilitation','elucidate','elucidating','illuminate',
  'illuminating','illuminated','invaluable','cutting-edge','innovative','innovation','align',
  'aligns','aligning','alignment','dynamic','dynamics','impactful','agile','scalable',
  'scalability','proactive','proactively','synergistic','optimize','optimizing','optimization',
  'resonate','resonating','resonated','resonates','underscore','underscored','cultivate',
  'cultivating','cultivated','galvanize','galvanizing','invigorate','invigorating','juxtapose',
  'juxtaposing','juxtaposition','underscore','bolster','augment','augmenting','augmented',
  'proliferate','proliferating','proliferation','burgeoning','nascent','ubiquitous','plethora',
  'myriad','quintessential','eclectic','indelible','overarching','underpinning','underpinnings',
];

const TIER_3 = [
  'significant','significantly','important','importantly','effective','effectively','efficient',
  'efficiently','diverse','diversity','unique','uniquely','key','vital','vitally','critical',
  'critically','essential','essentially','valuable','notable','remarkable','remarkably',
  'substantial','substantially','considerable','considerably','noteworthy','prominent',
  'prominently','influential','thoughtful','thoughtfully','insightful','insightfully','meaningful',
  'meaningfully','purposeful','purposefully','deliberate','deliberately','strategic',
  'strategically','integral','indispensable','instrumental','imperative','exemplary','commendable',
  'praiseworthy','sophisticated','profound','compelling','captivating','exquisite','impeccable',
  'formidable','stellar','exceptional','exceptionally','extraordinary','unparalleled',
  'unprecedented','monumental','groundbreaking','trailblazing','visionary','world-class',
  'state-of-the-art','best-in-class',
];

const AI_PHRASES = [
  { pattern: /\bin today'?s (digital age|fast-paced world|rapidly evolving|ever-changing|modern|interconnected)\b/gi, fix: '(remove or be specific about what changed)' },
  { pattern: /\bin today'?s world\b/gi, fix: '(remove or be specific)' },
  { pattern: /\bit is (worth|important to|essential to|crucial to) not(e|ing) that\b/gi, fix: '(remove — just state the fact)' },
  { pattern: /\bit should be noted that\b/gi, fix: '(remove — just state the fact)' },
  { pattern: /\bit bears mentioning that\b/gi, fix: '(remove — just state the fact)' },
  { pattern: /\bpave the way (for|to)\b/gi, fix: 'enable / allow / lead to' },
  { pattern: /\bat the forefront of\b/gi, fix: 'leading / first in' },
  { pattern: /\bnavigate the (complexities|challenges|landscape)\b/gi, fix: 'handle / deal with / work through' },
  { pattern: /\bharness the (power|potential|capabilities) of\b/gi, fix: 'use' },
  { pattern: /\bembark on a journey\b/gi, fix: 'start / begin' },
  { pattern: /\bpush the boundaries\b/gi, fix: '(be specific about what changed)' },
  { pattern: /\bfoster a (culture|environment|atmosphere|sense) of\b/gi, fix: 'build / create / encourage' },
  { pattern: /\bunlock the (potential|power|full|true)\b/gi, fix: 'enable / use / improve' },
  { pattern: /\bserves as a testament\b/gi, fix: 'shows / proves / demonstrates' },
  { pattern: /\bplays a (crucial|pivotal|vital|key|significant|important|critical) role\b/gi, fix: 'matters for / helps / is important to' },
  { pattern: /\bin the realm of\b/gi, fix: 'in' },
  { pattern: /\bdelve into\b/gi, fix: 'explore / examine / look at' },
  { pattern: /\bthe landscape of\b/gi, fix: '(be specific — what part of the field?)' },
  { pattern: /\bnestled (in|within|among)\b/gi, fix: 'located in / in / near' },
  { pattern: /\brise to the (occasion|challenge)\b/gi, fix: 'handle / face / tackle' },
  { pattern: /\bstand at the (crossroads|intersection)\b/gi, fix: '(be specific about the choice)' },
  { pattern: /\bshape the (future|trajectory|direction)\b/gi, fix: '(be specific about how)' },
  { pattern: /\btip of the iceberg\b/gi, fix: 'one example / a small part' },
  { pattern: /\bdouble-edged sword\b/gi, fix: 'has tradeoffs / cuts both ways' },
  { pattern: /\ba testament to\b/gi, fix: 'shows / proves' },
  { pattern: /\bthe dawn of\b/gi, fix: 'the start of / the beginning of' },
  { pattern: /\bthe fabric of\b/gi, fix: '(be concrete)' },
  { pattern: /\bthe tapestry of\b/gi, fix: '(be concrete)' },
  { pattern: /\bcould potentially\b/gi, fix: 'could / might' },
  { pattern: /\bmight possibly\b/gi, fix: 'might' },
  { pattern: /\bcould possibly\b/gi, fix: 'could' },
  { pattern: /\bperhaps potentially\b/gi, fix: 'perhaps / maybe' },
  { pattern: /\bmay potentially\b/gi, fix: 'may' },
  { pattern: /\bcould conceivably\b/gi, fix: 'could' },
  { pattern: /\bI hope this helps\b/gi, fix: '(remove)' },
  { pattern: /\blet me know if (you|there)\b/gi, fix: '(remove)' },
  { pattern: /\bwould you like me to\b/gi, fix: '(remove)' },
  { pattern: /\bfeel free to\b/gi, fix: '(remove)' },
  { pattern: /\bdon'?t hesitate to\b/gi, fix: '(remove)' },
  { pattern: /\bhappy to help\b/gi, fix: '(remove)' },
  { pattern: /\bhere is (a |an |the )?(comprehensive |brief |quick )?(overview|summary|breakdown|list|guide|explanation|look)\b/gi, fix: '(remove — start with the content)' },
  { pattern: /\bI'?d be happy to\b/gi, fix: '(remove)' },
  { pattern: /\bis there anything else\b/gi, fix: '(remove)' },
  { pattern: /\bgreat question\b/gi, fix: '(remove)' },
  { pattern: /\bexcellent (question|point|observation)\b/gi, fix: '(remove)' },
  { pattern: /\bthat'?s a (great|excellent|wonderful|fantastic|good|insightful|thoughtful) (question|point|observation)\b/gi, fix: '(remove)' },
  { pattern: /\byou'?re absolutely right\b/gi, fix: '(remove or address the substance)' },
  { pattern: /\byou raise a (great|good|excellent|valid|important) point\b/gi, fix: '(remove or address the substance)' },
  { pattern: /\bas of (my|this) (last|latest|most recent) (training|update|knowledge)\b/gi, fix: '(remove)' },
  { pattern: /\bwhile (specific )?details are (limited|scarce|not available)\b/gi, fix: '(remove — research it or omit the claim)' },
  { pattern: /\bbased on (available|my|current) (information|knowledge|understanding|data)\b/gi, fix: '(remove)' },
  { pattern: /\bup to my (last )?training\b/gi, fix: '(remove)' },
  { pattern: /\bthe future (looks|is|remains) bright\b/gi, fix: '(end with a specific fact or plan)' },
  { pattern: /\bexciting times (lie|lay|are) ahead\b/gi, fix: '(end with a specific fact or plan)' },
  { pattern: /\bcontinue (this|their|our|the) journey\b/gi, fix: '(be specific about what happens next)' },
  { pattern: /\bjourney toward(s)? (excellence|success|greatness)\b/gi, fix: '(be specific)' },
  { pattern: /\bstep in the right direction\b/gi, fix: '(be specific about the outcome)' },
  { pattern: /\bonly time will tell\b/gi, fix: '(end with what you actually know)' },
  { pattern: /\bthe possibilities are (endless|limitless|infinite)\b/gi, fix: "(be specific about what's possible)" },
  { pattern: /\bpoised for (growth|success|greatness|expansion)\b/gi, fix: '(cite evidence or remove)' },
  { pattern: /\bwatch this space\b/gi, fix: '(end with something concrete)' },
  { pattern: /\bstay tuned\b/gi, fix: '(end with something concrete)' },
  { pattern: /\bremains to be seen\b/gi, fix: '(state what you do know)' },
  { pattern: /\bin order to\b/gi, fix: 'to' },
  { pattern: /\bdue to the fact that\b/gi, fix: 'because' },
  { pattern: /\bat this point in time\b/gi, fix: 'now' },
  { pattern: /\bin the event that\b/gi, fix: 'if' },
  { pattern: /\bhas the ability to\b/gi, fix: 'can' },
  { pattern: /\bfor the purpose of\b/gi, fix: 'to / for' },
  { pattern: /\bin light of the fact that\b/gi, fix: 'because / since' },
  { pattern: /\bfirst and foremost\b/gi, fix: 'first' },
  { pattern: /\blast but not least\b/gi, fix: 'finally' },
  { pattern: /\bat the end of the day\b/gi, fix: '(remove or be specific)' },
  { pattern: /\bwhen it comes to\b/gi, fix: 'for / regarding' },
  { pattern: /\bthe fact of the matter is\b/gi, fix: '(remove — just state it)' },
  { pattern: /\bin terms of\b/gi, fix: 'for / about / regarding' },
  { pattern: /\bat its core\b/gi, fix: '(remove or be specific)' },
  { pattern: /\bit goes without saying\b/gi, fix: "(if it goes without saying, don't say it)" },
  { pattern: /\bneedless to say\b/gi, fix: "(if needless to say, don't say it)" },
];

const FUNCTION_WORDS = new Set([
  'the','be','to','of','and','a','in','that','have','i','it','for','not','on','with','he','as',
  'you','do','at','this','but','his','by','from','they','we','say','her','she','or','an','will',
  'my','one','all','would','there','their','what','so','up','out','if','about','who','get','which',
  'go','me','when','make','can','like','time','no','just','him','know','take','people','into','year',
  'your','good','some','could','them','see','other','than','then','now','look','only','come','its',
  'over','think','also','back','after','use','two','how','our','work','first','well','way','even',
  'new','want','because','any','these','give','day','most','us',
]);

// ─── Structural phrase lists ─────────────────────────────

const SIGNIFICANCE_PHRASES = [
  /marking a pivotal/gi, /pivotal moment/gi, /pivotal role/gi, /key role/gi, /crucial role/gi,
  /vital role/gi, /significant role/gi, /is a testament/gi, /stands as a testament/gi,
  /serves as a testament/gi, /serves as a reminder/gi, /reflects broader/gi, /broader trends/gi,
  /broader movement/gi, /evolving landscape/gi, /evolving world/gi, /setting the stage for/gi,
  /marking a shift/gi, /key turning point/gi, /indelible mark/gi, /deeply rooted/gi, /focal point/gi,
  /symbolizing its ongoing/gi, /enduring legacy/gi, /lasting impact/gi, /contributing to the/gi,
  /underscores the importance/gi, /highlights the significance/gi, /represents a shift/gi,
  /shaping the future/gi, /the evolution of/gi, /rich tapestry/gi, /rich heritage/gi,
  /stands as a beacon/gi, /marks a milestone/gi, /paving the way/gi, /charting a course/gi,
];

const PROMOTIONAL_WORDS = [
  /\bnestled\b/gi, /\bin the heart of\b/gi, /\bbreathtaking\b/gi, /\bmust-visit\b/gi, /\bstunning\b/gi,
  /\brenowned\b/gi, /\bnatural beauty\b/gi, /\brich cultural heritage\b/gi, /\brich history\b/gi,
  /\bcommitment to\b/gi, /\bexemplifies\b/gi, /\bworld-class\b/gi, /\bstate-of-the-art\b/gi,
  /\bgame-changing\b/gi, /\bgame changer\b/gi, /\bunparalleled\b/gi, /\bprofound\b/gi,
  /\bbest-in-class\b/gi, /\btrailblazing\b/gi, /\bvisionary\b/gi, /\bcutting-edge\b/gi,
  /\bworldwide recognition\b/gi,
];

const VAGUE_ATTRIBUTION_PHRASES = [
  /\bexperts (believe|argue|say|suggest|note|agree|contend|have noted)\b/gi,
  /\bindustry (reports|observers|experts|analysts|leaders|insiders)\b/gi,
  /\bobservers have (cited|noted|pointed out)\b/gi, /\bsome critics argue\b/gi,
  /\bsome experts (say|believe|suggest)\b/gi, /\bseveral sources\b/gi, /\baccording to reports\b/gi,
  /\bwidely (regarded|considered|recognized|acknowledged)\b/gi,
  /\bit is widely (known|believed|accepted)\b/gi,
  /\bmany (experts|scholars|researchers|analysts) (believe|argue|suggest)\b/gi,
  /\bstudies (show|suggest|indicate|have shown)\b/gi,
  /\bresearch (shows|suggests|indicates|has shown)\b/gi, /\bsources close to\b/gi,
  /\bpeople familiar with\b/gi,
];

const CHALLENGES_PHRASES = [
  /despite (its|these|the|their) (challenges|setbacks|obstacles|difficulties|limitations)/gi,
  /faces (several|many|numerous|various) challenges/gi, /continues to thrive/gi,
  /continues to grow/gi, /future (outlook|prospects) (remain|look|appear)/gi,
  /challenges and (future|legacy|opportunities)/gi, /despite these (challenges|hurdles|obstacles)/gi,
  /overcoming (obstacles|challenges|adversity)/gi, /weather(ing|ed) the storm/gi,
];

const COPULA_AVOIDANCE = [
  /\bserves as( a)?\b/gi, /\bstands as( a)?\b/gi, /\bmarks a\b/gi, /\brepresents a\b/gi,
  /\bboasts (a|an|over|more)\b/gi, /\bfeatures (a|an|over|more)\b/gi, /\boffers (a|an)\b/gi,
  /\bfunctions as\b/gi, /\bacts as( a)?\b/gi, /\boperates as( a)?\b/gi,
];

// ─── Counting helpers ────────────────────────────────────

function countRegex(text, regex) {
  const g = new RegExp(regex.source, regex.flags.includes('g') ? regex.flags : regex.flags + 'g');
  const m = text.match(g);
  return m ? m.length : 0;
}

function countList(text, regexList) {
  return regexList.reduce((n, r) => n + countRegex(text, r), 0);
}

function wordRegex(word) {
  const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp('\\b' + escaped + '\\b', 'gi');
}

function countWordList(text, words) {
  return words.reduce((n, w) => n + countRegex(text, wordRegex(w)), 0);
}

function countPhrases(text, phrases) {
  return phrases.reduce((n, p) => n + countRegex(text, p.pattern), 0);
}

function wordCount(text) {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

// ─── Statistics (stylometric signals) ────────────────────

function tokenize(text) {
  return text.toLowerCase().replace(/[^\w\s'-]/g, ' ').split(/\s+/).filter((w) => w.length > 0);
}

function splitSentences(text) {
  const cleaned = text
    .replace(/\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|etc|vs|approx|dept|est|vol)\./gi, '$1․')
    .replace(/\b([A-Z])\./g, '$1․')
    .replace(/\b(\d+)\./g, '$1․');
  return cleaned
    .split(/(?<=[.!?])\s+(?=[A-Z"'“])|(?<=[.!?])$/)
    .map((s) => s.replace(/․/g, '.').trim())
    .filter((s) => s.length > 0);
}

function estimateSyllables(word) {
  word = word.toLowerCase().replace(/[^a-z]/g, '');
  if (word.length <= 3) return 1;
  const vowelGroups = word.match(/[aeiouy]+/g);
  let count = vowelGroups ? vowelGroups.length : 1;
  if (word.endsWith('e') && !word.endsWith('le')) count--;
  if (word.endsWith('ed') && word.length > 3 && !/[aeiouy]ed$/.test(word)) count--;
  return Math.max(count, 1);
}

function ngramRepetition(words, n) {
  if (words.length < n) return 0;
  const grams = {};
  for (let i = 0; i <= words.length - n; i++) {
    const g = words.slice(i, i + n).join(' ');
    grams[g] = (grams[g] || 0) + 1;
  }
  const total = Object.keys(grams).length;
  if (total === 0) return 0;
  return Object.values(grams).filter((c) => c > 1).length / total;
}

function round(n) {
  return Math.round(n * 1000) / 1000;
}

function computeStats(text) {
  const words = tokenize(text);
  const sentences = splitSentences(text);
  const paragraphs = text.split(/\n\s*\n/).filter((p) => p.trim().length > 0);
  const wc = words.length;
  if (wc === 0) return { wordCount: 0, sentenceCount: 0, paragraphCount: 0 };

  const uniqueWords = new Set(words);
  const typeTokenRatio = uniqueWords.size / wc;

  const sentenceLengths = sentences.map((s) => tokenize(s).length).filter((k) => k > 0);
  const sentenceCount = sentenceLengths.length;

  let avgSentenceLength = 0, sentenceLengthStdDev = 0, sentenceLengthVariation = 0, burstiness = 0;
  if (sentenceCount > 1) {
    avgSentenceLength = sentenceLengths.reduce((a, b) => a + b, 0) / sentenceCount;
    const variance = sentenceLengths.reduce((s, l) => s + Math.pow(l - avgSentenceLength, 2), 0) / sentenceCount;
    sentenceLengthStdDev = Math.sqrt(variance);
    sentenceLengthVariation = avgSentenceLength > 0 ? sentenceLengthStdDev / avgSentenceLength : 0;
    let diffSum = 0;
    for (let i = 1; i < sentenceLengths.length; i++) diffSum += Math.abs(sentenceLengths[i] - sentenceLengths[i - 1]);
    const avgDiff = diffSum / (sentenceLengths.length - 1);
    burstiness = avgSentenceLength > 0 ? avgDiff / avgSentenceLength : 0;
  } else if (sentenceCount === 1) {
    avgSentenceLength = sentenceLengths[0];
  }

  const fnWordCount = words.filter((w) => FUNCTION_WORDS.has(w)).length;
  const syllables = words.reduce((s, w) => s + estimateSyllables(w), 0);
  const fleschKincaid = sentenceCount > 0
    ? 0.39 * (wc / sentenceCount) + 11.8 * (syllables / wc) - 15.59 : 0;

  return {
    wordCount: wc,
    sentenceCount,
    paragraphCount: paragraphs.length,
    avgSentenceLength: round(avgSentenceLength),
    sentenceLengthStdDev: round(sentenceLengthStdDev),
    sentenceLengthVariation: round(sentenceLengthVariation),
    burstiness: round(burstiness),
    typeTokenRatio: round(typeTokenRatio),
    functionWordRatio: round(fnWordCount / wc),
    trigramRepetition: round(ngramRepetition(words, 3)),
    fleschKincaid: round(fleschKincaid),
  };
}

function computeUniformityScore(stats) {
  if (!stats.wordCount) return 0;
  let score = 0;
  if (stats.burstiness < 0.2) score += 25;
  else if (stats.burstiness < 0.35) score += 18;
  else if (stats.burstiness < 0.5) score += 10;
  else if (stats.burstiness < 0.65) score += 5;

  if (stats.sentenceLengthVariation < 0.2) score += 25;
  else if (stats.sentenceLengthVariation < 0.35) score += 18;
  else if (stats.sentenceLengthVariation < 0.5) score += 10;
  else if (stats.sentenceLengthVariation < 0.65) score += 5;

  if (stats.wordCount > 100) {
    if (stats.typeTokenRatio < 0.35) score += 20;
    else if (stats.typeTokenRatio < 0.45) score += 12;
    else if (stats.typeTokenRatio < 0.55) score += 5;
  }

  if (stats.trigramRepetition > 0.15) score += 15;
  else if (stats.trigramRepetition > 0.1) score += 10;
  else if (stats.trigramRepetition > 0.05) score += 5;

  if (stats.paragraphCount >= 3 && stats.sentenceCount > 5) {
    if (stats.sentenceLengthStdDev < 3 && stats.avgSentenceLength > 10) score += 15;
  }
  return Math.min(score, 100);
}

// ─── Pattern detectors (24) ──────────────────────────────

function aiVocabCount(text) {
  const words = wordCount(text);
  let n = countWordList(text, TIER_1);
  const tier2 = countWordList(text, TIER_2);
  if (tier2 >= 2) n += tier2;
  if (words > 50) {
    const tier3 = countWordList(text, TIER_3);
    if (tier3 / words > 0.03) n += tier3;
  }
  const phrase7 = AI_PHRASES.filter(
    (p) => p.fix && !p.fix.startsWith('(remove') &&
      !['to', 'because', 'now', 'if', 'can', 'first', 'finally'].includes(p.fix),
  );
  n += countPhrases(text, phrase7);
  return n;
}

function ruleOfThree(text) {
  const buzzyTriad = /\b(\w+tion|\w+ity|\w+ment|\w+ness|\w+ance|\w+ence),\s+(\w+tion|\w+ity|\w+ment|\w+ness|\w+ance|\w+ence),\s+and\s+(\w+tion|\w+ity|\w+ment|\w+ness|\w+ance|\w+ence)\b/gi;
  const adj = ['seamless','intuitive','powerful','innovative','dynamic','robust','comprehensive',
    'cutting-edge','scalable','agile','efficient','effective','engaging','impactful','meaningful',
    'transformative','sustainable','resilient','inclusive','accessible'].join('|');
  const adjTriad = new RegExp('\\b(' + adj + '),\\s+(' + adj + '),\\s+and\\s+(' + adj + ')\\b', 'gi');
  return countRegex(text, buzzyTriad) + countRegex(text, adjTriad);
}

function synonymCycling(text) {
  const sets = [
    ['protagonist','main character','central figure','hero','lead character','lead'],
    ['company','firm','organization','enterprise','corporation','establishment','entity'],
    ['city','metropolis','urban center','municipality','locale','township'],
    ['building','structure','edifice','facility','complex','establishment'],
    ['tool','instrument','mechanism','apparatus','device','utility'],
    ['country','nation','state','republic','sovereign state'],
    ['problem','challenge','issue','obstacle','hurdle','difficulty'],
    ['solution','approach','methodology','framework','strategy','paradigm'],
  ];
  const sentences = text.split(/[.!?]+/).filter((s) => s.trim().length > 0);
  let n = 0;
  for (const syns of sets) {
    for (let i = 0; i < sentences.length - 1; i++) {
      const found = [];
      for (let j = i; j < Math.min(i + 4, sentences.length); j++) {
        const lower = sentences[j].toLowerCase();
        for (const syn of syns) if (lower.includes(syn) && !found.includes(syn)) found.push(syn);
      }
      if (found.length >= 3) { n++; break; }
    }
  }
  return n;
}

function titleCaseHeadings(text) {
  const headingRegex = /^#{1,6}\s+(.+)$/gm;
  const skip = /^(I|AI|API|CLI|URL|HTML|CSS|JS|TS|NPM|NYC|USA|UK|EU|LLM|GPT|SaaS|IoT|CEO|CTO|VP|PR|HR|IT|UI|UX)\b/;
  let n = 0, m;
  while ((m = headingRegex.exec(text)) !== null) {
    const words = m[1].trim().split(/\s+/);
    if (words.length >= 3) {
      const caps = words.filter((w) => /^[A-Z]/.test(w) && !skip.test(w)).length;
      if (caps / words.length > 0.7) n++;
    }
  }
  return n;
}

function phrasesByFix(pred) {
  return AI_PHRASES.filter((p) => p.fix && pred(p));
}

// Each detector -> integer match count. Threshold-gated ones return 0 until the
// gate trips, matching the source engine so scores line up byte-for-byte.
const DETECTORS = [
  { id: 1, category: 'content', weight: 4, count: (t) => countList(t, SIGNIFICANCE_PHRASES) },
  { id: 2, category: 'content', weight: 3, count: (t) => {
      const media = /\b(cited|featured|covered|mentioned|reported|published|recognized|highlighted) (in|by) .{0,20}(The New York Times|BBC|CNN|The Washington Post|The Guardian|Wired|Forbes|Reuters|Bloomberg|Financial Times|The Verge|TechCrunch|The Hindu|Al Jazeera|Time|Newsweek|The Economist|Nature|Science).{0,100}(,\s*(and\s+)?(The New York Times|BBC|CNN|The Washington Post|The Guardian|Wired|Forbes|Reuters|Bloomberg|Financial Times|The Verge|TechCrunch|The Hindu|Al Jazeera|Time|Newsweek|The Economist|Nature|Science))+/gi;
      return countRegex(t, media) + countRegex(t, /\bactive social media presence\b/gi) +
        countRegex(t, /\bwritten by a leading expert\b/gi) +
        countRegex(t, /\bhas been (featured|recognized|acknowledged) (by|in)\b/gi);
    } },
  { id: 3, category: 'content', weight: 4, count: (t) => countRegex(t, /,\s*(highlighting|underscoring|emphasizing|ensuring|reflecting|symbolizing|contributing to|cultivating|fostering|encompassing|showcasing|demonstrating|illustrating|representing|signaling|indicating|solidifying|reinforcing|cementing|bolstering|reaffirming|illuminating|epitomizing)\b[^.]{5,}/gi) },
  { id: 4, category: 'content', weight: 3, count: (t) => countList(t, PROMOTIONAL_WORDS) },
  { id: 5, category: 'content', weight: 4, count: (t) => countList(t, VAGUE_ATTRIBUTION_PHRASES) },
  { id: 6, category: 'content', weight: 3, count: (t) => countList(t, CHALLENGES_PHRASES) },
  { id: 7, category: 'language', weight: 5, count: aiVocabCount },
  { id: 8, category: 'language', weight: 3, count: (t) => countList(t, COPULA_AVOIDANCE) },
  { id: 9, category: 'language', weight: 3, count: (t) =>
      countRegex(t, /\b(it'?s|this is) not (just|merely|only|simply) .{3,60}(,|;|—)\s*(it'?s|this is|but)\b/gi) +
      countRegex(t, /\bnot only .{3,60} but (also )?\b/gi) },
  { id: 10, category: 'language', weight: 2, count: ruleOfThree },
  { id: 11, category: 'language', weight: 2, count: synonymCycling },
  { id: 12, category: 'language', weight: 2, count: (t) =>
      countRegex(t, /\bfrom .{3,40} to .{3,40},\s*from .{3,40} to .{3,40}/gi) +
      countRegex(t, /\bfrom (the )?(dawn|birth|inception|beginning|advent|emergence|rise|earliest) .{3,60} to (the )?(modern|current|present|contemporary|latest|cutting-edge|digital|future)/gi) },
  { id: 13, category: 'style', weight: 2, count: (t) => {
      const em = countRegex(t, /—/g); const w = wordCount(t);
      const ratio = w > 0 ? em / (w / 100) : 0;
      return (ratio > 1.0 && em >= 2) ? em : 0;
    } },
  { id: 14, category: 'style', weight: 2, count: (t) => {
      const b = countRegex(t, /\*\*[^*]+\*\*/g); return b >= 3 ? b : 0;
    } },
  { id: 15, category: 'style', weight: 3, count: (t) => {
      const h = countRegex(t, /^[*-]\s+\*\*[^*]+:\*\*\s/gm); return h >= 2 ? h : 0;
    } },
  { id: 16, category: 'style', weight: 1, count: titleCaseHeadings },
  { id: 17, category: 'style', weight: 2, count: (t) => {
      const e = countRegex(t, /[\u{1F300}-\u{1F9FF}\u{2600}-\u{27BF}]/gu);
      return e >= 3 ? countRegex(t, /[\u{1F300}-\u{1F9FF}\u{2600}-\u{27BF}\u{2300}-\u{23FF}\u{2B50}]/gu) : 0;
    } },
  { id: 18, category: 'style', weight: 1, count: (t) => countRegex(t, /[“”‘’]/g) },
  { id: 19, category: 'communication', weight: 5, count: (t) =>
      countPhrases(t, phrasesByFix((p) => p.fix === '(remove)' || p.fix === '(remove — start with the content)')) },
  { id: 20, category: 'communication', weight: 4, count: (t) =>
      countPhrases(t, phrasesByFix((p) => p.fix === '(remove)' &&
        (p.pattern.source.includes('training') || p.pattern.source.includes('details are') || p.pattern.source.includes('available')))) },
  { id: 21, category: 'communication', weight: 4, count: (t) =>
      countPhrases(t, phrasesByFix((p) => (p.fix.includes('(remove)') || p.fix.includes('address the substance')) &&
        (p.pattern.source.includes('question') || p.pattern.source.includes('point') || p.pattern.source.includes('right') || p.pattern.source.includes('observation')))) },
  { id: 22, category: 'filler', weight: 3, count: (t) =>
      countPhrases(t, phrasesByFix((p) => !p.fix.startsWith('(') &&
        ['to','because','now','if','can','to / for','first','finally','for / regarding','because / since'].includes(p.fix))) },
  { id: 23, category: 'filler', weight: 3, count: (t) =>
      countPhrases(t, phrasesByFix((p) => p.fix.includes('could') || p.fix.includes('might') || p.fix.includes('may') || p.fix.includes('perhaps') || p.fix.includes('maybe'))) },
  { id: 24, category: 'filler', weight: 3, count: (t) =>
      countPhrases(t, phrasesByFix((p) => p.fix.includes('specific fact') || p.fix.includes('concrete') || p.fix.includes('cite evidence') || p.fix.includes('what you do know') || p.fix.includes('what happens next'))) },
];

// ─── Scoring ─────────────────────────────────────────────

function patternScore(findings, words) {
  if (words === 0 || findings.length === 0) return 0;
  let weighted = 0;
  for (const f of findings) weighted += f.matchCount * f.weight;
  const density = (weighted / words) * 100;
  const densityScore = Math.min(Math.log2(density + 1) * 13, 65);
  const breadthBonus = Math.min(findings.length * 2, 20);
  const categoriesHit = new Set(findings.map((f) => f.category)).size;
  const categoryBonus = Math.min(categoriesHit * 3, 15);
  return Math.min(Math.round(densityScore + breadthBonus + categoryBonus), 100);
}

function compositeScore(pScore, uScore, findings) {
  if (pScore === 0 && uScore === 0) return 0;
  if (findings.length === 0) return Math.min(Math.round(uScore * 0.15), 15);
  return Math.min(Math.round(pScore * 0.7 + uScore * 0.3), 100);
}

function analyze(text) {
  const trimmed = (text || '').trim();
  if (!trimmed) return { score: 0, patternScore: 0, uniformityScore: 0, totalMatches: 0, wordCount: 0, findings: [], stats: null };

  const words = wordCount(trimmed);
  const stats = computeStats(trimmed);
  const uniformityScore = (stats.wordCount >= 20 && stats.sentenceCount >= 3)
    ? computeUniformityScore(stats) : 0;

  const findings = [];
  for (const d of DETECTORS) {
    const c = d.count(trimmed);
    if (c > 0) findings.push({ id: d.id, category: d.category, weight: d.weight, matchCount: c });
  }

  const pScore = patternScore(findings, words);
  const score = compositeScore(pScore, uniformityScore, findings);
  const totalMatches = findings.reduce((s, f) => s + f.matchCount, 0);

  return { score, patternScore: pScore, uniformityScore, totalMatches, wordCount: words, findings, stats };
}

// ─── CLI ─────────────────────────────────────────────────

function main() {
  const args = process.argv.slice(2);
  const json = args.includes('--json');
  const fileArg = args.find((a) => !a.startsWith('--'));

  let text;
  if (fileArg) {
    text = require('fs').readFileSync(fileArg, 'utf8');
  } else {
    text = require('fs').readFileSync(0, 'utf8');
  }

  const result = analyze(text);
  if (json) {
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  } else {
    process.stdout.write(result.score + '\n');
  }
}

if (require.main === module) main();

module.exports = { analyze, computeStats, computeUniformityScore, DETECTORS };
