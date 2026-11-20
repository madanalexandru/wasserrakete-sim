# Vorab-Notiz: Wirkung des Expansionsexponenten auf das Apogäum

Festgelegt: 20.11.2026, vor der Messung.

## 1 Frage

Wie stark verschiebt ein Expansionsexponent β von 1,17, 1,20 und 1,22
statt γ = 1,4 in der Wasserphase das Apogäum?

Hintergrund: Romanelli, Bove & González Madina (2013, S. 764, Tab. I)
maßen an einer festgehaltenen Flasche bei Druckverhältnissen von 3,2 bis
4,8 einen polytropen Exponenten von 1,17 bis 1,22, weil Wasserdampf
kondensiert. Die Schwelle S des Tool-Vergleichs enthält nur die
c_w-Unsicherheit. Dieses Experiment beziffert eine weitere, bekannte
Unsicherheit. Es ändert weder S noch einen KPI.

## 2 Umsetzung

- Direkt in der Physik, ohne API (wie experiments/ereignissuche). Der
  Code in backend/app bleibt unverändert; MODEL_VERSION bleibt "1".
- Nur zur Laufzeit im Skript und nur in der Wasserphase:
  - Druck: p = p0 · (V_L,0 / V_L)^β (Konstante GAMMA in waterphase.py),
  - Temperatur am Ende der Wasserphase: T = T0 · (p / p0)^((β − 1)/β)
    (polytrop, passend zum Druck).
- Der Luftstoß bleibt isentrop mit γ = 1,4 (Annahme: Romanelli maß
  während des Wasserausstoßes, nicht im Luftstoß).
- Nach jedem Lauf werden die Originalwerte wiederhergestellt.

## 3 Raketen und Werte

- R0–R9 und E1–E4 wie im Tool-Vergleich bzw. in der Stichprobe, jeweils
  mit c_w' = 0,345 · 1,2039 / 1,225.
- β ∈ {1,4 (Kontrolle); 1,17; 1,20; 1,22}.

## 4 Kontrolle

Mit β = 1,4 (ohne jede Änderung) muss das Apogäum jeder Rakete bitgleich
mit h_modell aus tool_vergleich/results/vergleich.csv (R0–R9) bzw.
stichprobe/results/stichprobe.csv (E1–E4) sein. Sonst wird nichts
ausgewertet; die Ursache wird untersucht und berichtet.

## 5 Kennzahlen (beschreibend, ohne KPI)

- Δβ = (h(β) − h(1,4)) / h(1,4) je Rakete und β, in %.
- Je β: kleinster und größter Wert über alle 14 Raketen.
- Je β: Zahl der Raketen mit |Δβ| > S (S aus denselben Dateien wie oben).

## 6 Grenzen

- Romanelli maß an einer festgehaltenen Flasche und nur bei
  Druckverhältnissen 3,2–4,8; nicht alle Raketen liegen darin.
- β gilt hier für die ganze Wasserphase und für alle Raketen gleich.
- Der Luftstoß bleibt bei γ = 1,4.

## 7 Vorwissen (offengelegt)

Eine Vorabrechnung der KI in ihrer eigenen Rechenumgebung (19.11.2026,
nicht im Repository) ergab für einen Exponenten von 1,2 nur in der
Wasserphase: R0 +6,7 %, R1 +8,8 %, R7 +8,0 %, R8 +13,7 %, jeweils
größer als S. Ob sie auch die Temperatur angepasst hat, ist nicht
dokumentiert. Dieselben Zahlen standen in einem KI-Gutachten. Die
Messung ist also nicht blind.