# PRScope: Machine Learning vs. Deterministic AST Analysis
**DevJams'26 | Team CommitZero**

## Executive Summary
This document outlines our engineering investigation into whether a machine learning layer could outperform our deterministic AST (Abstract Syntax Tree) rule engine for detecting cross-PR structural relationships. 

After extracting structural features (e.g., AST symbol overlaps, call graph intersections, and signature modifications) and testing four distinct ML architectures, we concluded that **strict deterministic logic is mathematically superior to statistical models for this problem domain and dataset size.** We have locked the deterministic AST engine as our final DevJams MVP[cite: 5].

---

## 1. The Dataset & The Class Imbalance Problem
We evaluated our pipeline against 198 validated PR pairs derived from the BulkPR-Bench dataset[cite: 1, 5]. The target classification task suffers from extreme, real-world class imbalance:
* **INDEPENDENT:** 150 pairs[cite: 1]
* **CONFLICT:** 32 pairs[cite: 1]
* **DEPENDENCY:** 16 pairs[cite: 1]

## 2. The Baseline (Deterministic Rule Engine)
Our hardcoded rule engine relies on a strict programmatic contract: *if PR A modifies a symbol's AST context and PR B calls that same symbol, it is a conflict*[cite: 4].
* **CONFLICT F1:** 0.702[cite: 5]
* **DEPENDENCY F1:** 0.800[cite: 5]
* **INDEPENDENT F1:** 0.945[cite: 5]

The goal of the ML experiments was to beat these baseline F1 scores using numeric structural features.

---

## 3. The Machine Learning Experiments

### Experiment A: Standard LightGBM
* **Hypothesis:** Gradient boosting can map non-linear relationships between feature overlaps.
* **Result:** **Failed.** The model severely overfit on raw size metrics (e.g., total lines of code added) rather than structural overlap. F1 scores dropped across all classes (CONFLICT: 0.655, DEPENDENCY: 0.645). 

### Experiment B: Two-Stage Cascaded Architecture
* **Hypothesis:** To protect against the massive 150-pair INDEPENDENT class[cite: 1], we built Stage 1 to separate INDEPENDENT vs. RELATED, and Stage 2 to separate CONFLICT vs. DEPENDENCY.
* **Result:** **Failed.** Stage 2 suffered from data starvation. With only 16 total DEPENDENCY pairs[cite: 1], our 4-fold cross-validation left only 12 training examples per fold. The tree-based binning broke down entirely, dropping DEPENDENCY F1 to an absolute 0.000.

### Experiment C: L2-Regularized Logistic Regression
* **Hypothesis:** Linear models evaluate continuous weights rather than hard splits, allowing them to extract signal from minority classes on micro-datasets without collapsing.
* **Result:** **Partial Recovery.** Using `StandardScaler` and balanced class weights, the DEPENDENCY F1 recovered to 0.727. However, CONFLICT precision collapsed to 0.486, introducing an unacceptable volume of false positives. It still failed to beat the deterministic baseline.

### Experiment D: Asymmetric Rule-Veto Ensemble
* **Hypothesis:** Use the deterministic engine first. If it detects a relationship, trust it completely. Only pass the data to the ML model if the rule engine defaults to INDEPENDENT, attempting to catch hidden edge cases.
* **Result:** **Failed.** While this protected the True Positives, the ML model's false-positive rate dragged the overall F1 scores down (CONFLICT F1: 0.648, DEPENDENCY F1: 0.774).

---

## 4. Final Architectural Decision
We are shipping the **Deterministic AST Rule Engine** without a machine learning classifier.

**Why this matters for our MVP:**
1. **Explainability:** The rule engine provides 100% deterministic evidence (e.g., "PR 41 modified AuthToken.validate(), which PR 57 calls") rather than a statistical black-box probability[cite: 5].
2. **Micro-Dataset Resilience:** The "defines vs. modifies" relationship is a strict logical boundary[cite: 4]. Tree-based statistical models require vastly larger datasets to learn this concept from raw numeric counts.
3. **Accuracy:** The deterministic engine remains undefeated on F1 score for this dataset.