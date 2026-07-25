# **AI-BASED SQL INJECTION DETECTION SYSTEM**

## **MIDTERM REPORT — Scope: Branch 1 (Supervised Classification) + Branch 2 (Anomaly Detection) only**

> Session-level detection (Branch 3), the full three-branch Decision Engine, and Continual Learning are **not** part of this midterm report. They appear only in **CONCLUSIONS → Future Work**, where the project's full multi-phase design is stated as work not yet started.

---

## **LIST OF ABBREVIATIONS**

| Abbreviation | Meaning |
| :---- | :---- |
| AI | Artificial Intelligence |
| ML | Machine Learning |
| SQLi | SQL Injection |
| WAF | Web Application Firewall |
| CRS | (OWASP) Core Rule Set |
| FPR | False Positive Rate |
| DR | Detection Rate |
| AUC | Area Under the (ROC) Curve |
| ROC | Receiver Operating Characteristic |
| PR | Precision–Recall |
| TF-IDF | Term Frequency – Inverse Document Frequency |
| SVM | Support Vector Machine |
| OCSVM | One-Class Support Vector Machine |
| CNN | Convolutional Neural Network |
| RNN | Recurrent Neural Network |
| LSTM | Long Short-Term Memory |
| GRU | Gated Recurrent Unit |
| NLP | Natural Language Processing |
| LLM | Large Language Model |
| XSS | Cross-Site Scripting |
| CSRF | Cross-Site Request Forgery |
| OOB | Out-of-Band (SQL Injection) |
| CSIC 2010 | Consejo Superior de Investigaciones Científicas 2010 (HTTP dataset) |
| API | Application Programming Interface |

*(Add/remove rows as needed once the final camera-ready text is set — this list should match exactly the abbreviations actually used in the final document.)*

## **LIST OF TABLES**

| # | Caption | Location |
| :---- | :---- | :---- |
| Table 1.1 | Comparison of Existing Detection Methods | Section 1.9 |
| Table 2.1 | Decision Table (Two-Branch Design, Midterm Scope) | Section 2.6 |
| Table 2.2 | Branch 1 Architecture Comparison | Section 2.8 |
| Table 2.3 | Branch 1 Per-Class Results (Test Set, n = 13,560) | Section 2.8 |
| Table 2.4 | Branch 2 Algorithm Comparison | Section 2.9 |
| Table 2.5 | Branch 2 Threshold Sweep (Selected Operating Points) | Section 2.9 |

## **LIST OF FIGURES**

This is the complete inventory of figures this report should have, with exactly where each one goes. Two (Figure 1.1, 1.2) are already embedded in this Markdown file as generic conceptual diagrams. The other four are real result plots already generated on disk — **insert these four manually** when transferring this content into the `.docx`.

| # | Caption | Source file | Insert at |
| :---- | :---- | :---- | :---- |
| Figure 1.1 | General CNN workflow for SQLi detection (generic/illustrative) | already embedded in this file (Section 1.5.1) | Section 1.5.1 |
| Figure 1.2 | General anomaly detection workflow (generic/illustrative) | already embedded in this file (Section 1.7) | Section 1.7 |
| Figure 2.1 | Branch 1 — per-class ROC curves | `report/metrics/figures/nhanh1_roc_per_class.png` | Section 2.8, right after Table 2.3 |
| Figure 2.2 | Branch 2 — Precision–Recall curve (OCSVM) | `report/metrics/figures/nhanh2_pr_curve.png` | Section 2.9, right after Table 2.4 |
| Figure 2.3 | Branch 2 — anomaly score distribution, benign vs. anomalous | `report/metrics/figures/nhanh2_score_dist.png` | Section 2.9, alongside Figure 2.2 |
| Figure 2.4 | Branch 2 — FPR/Detection-Rate threshold trade-off | `report/metrics/figures/nhanh2_threshold_tradeoff.png` | Section 2.9, right after Table 2.5 |

**Missing, recommended (not yet created):** a simple architecture diagram of the Database Proxy placement + two-branch decision flow (Section 2.1/2.6 would both benefit from this — currently text-only). Not blocking for the midterm submission, but worth adding before the final report.

---

## **INTRODUCTION**

### **Background**

With the rapid growth of web applications, protecting databases has become one of the most important tasks in cybersecurity. Modern websites store a large amount of sensitive information such as personal data, passwords, banking information, and business records. Because of this, databases are common targets for attackers.

SQL Injection (SQLi) is one of the oldest and most dangerous web vulnerabilities. It allows attackers to insert malicious SQL commands into user input fields. If the application does not validate user input correctly, these commands can be executed directly by the database management system. As a result, attackers may read confidential information, modify records, delete data, or even gain administrator privileges.

Although many organizations use Web Application Firewalls (WAFs) to protect their systems, traditional rule-based security solutions still have several limitations. They mainly rely on predefined signatures and manually written rules. New attack techniques, obfuscated payloads, and zero-day attacks can bypass these defenses. At the same time, strict rules may incorrectly classify normal queries as malicious, increasing the False Positive Rate (FPR).

Recently, Artificial Intelligence (AI) and Machine Learning (ML) have become promising technologies for cybersecurity. Instead of depending only on predefined rules, AI models can learn attack patterns from historical data and recognize previously unseen attacks. Deep learning models such as CNNs and Transformer-based models have shown high accuracy in many SQL Injection detection studies.

Therefore, this project proposes an AI-Based SQL Injection Detection System. **This midterm report covers the two components implemented and evaluated so far: a supervised classifier for known SQL Injection categories (Branch 1) and a query-level anomaly detector for previously unseen attack patterns (Branch 2).** Extending detection to the relationship between multiple queries in the same user session is part of the project's longer-term design and is discussed only as future work (Conclusions).

## **Research Objectives**

The main objective of this project is to develop an intelligent SQL Injection detection system using Artificial Intelligence techniques.

* Detect common SQL Injection attacks with high accuracy — addressed by Branch 1 (Section 2.8).
* Detect unknown or zero-day attacks through anomaly detection — addressed by Branch 2 (Section 2.9).
* Reduce False Positive Rate while maintaining fast response time — addressed by both branches' latency and FPR results (Section 2.8–2.9).

## **Scope of the Study**

The proposed system focuses on SQL Injection detection at the Database Proxy layer. The proxy receives SQL statements after the backend application has generated the final SQL query but before the query reaches the database server.

**This midterm report covers two detection components:**

* Supervised SQL Injection Classification (Branch 1)
* Query-level Anomaly Detection (Branch 2)

The following topics are outside the scope of the project entirely (not just deferred):

* Cross-Site Scripting (XSS)
* Cross-Site Request Forgery (CSRF)
* Second-order SQL Injection
* Out-of-band SQL Injection
* Network intrusion detection
* Malware analysis

## **Research Methodology**

This project follows an experimental research methodology.

First, datasets containing normal SQL queries and SQL Injection payloads are collected and preprocessed.

Second, AI models are trained and evaluated: a supervised multi-class classifier and a benign-only anomaly detector.

Third, both detection components are demonstrated together through an illustrative notebook (Section 2.10); a fully integrated Database Proxy service is not part of this midterm scope (see Section 2.6).

Finally, both components are evaluated using performance metrics appropriate to each: Precision, Recall, F1-score, and per-class ROC for the classifier; False Positive Rate, Detection Rate, AUC, and a Precision-Recall curve for the anomaly detector; both also report inference latency and model size.

---

# **CHAPTER 1. THEORY**

## **1.1 Overview of SQL Injection**

SQL Injection is one of the most common web security vulnerabilities. It occurs when user input is directly included in SQL statements without proper validation or parameterization.

Normally, a web application receives input from users through forms, search boxes, or URLs. The backend application combines these inputs into SQL statements before sending them to the database. If the application does not sanitize user input correctly, attackers can insert malicious SQL commands.

For example, a normal login query may be written as:

| SELECT * FROM users WHERE username='admin' AND password='123456'; |
| :---- |

An attacker may enter the following password:

| ' OR '1'='1 |
| :---- |

The SQL statement becomes:

| SELECT * FROM users WHERE username='admin' AND password='' OR '1'='1'; |
| :---- |

Since the condition `'1'='1'` is always true, the database returns all matching records, allowing unauthorized access.

## **1.2 Types of SQL Injection**

SQL Injection attacks can be divided into several categories depending on how attackers exploit the database. Understanding these attack types is important because they are also used as labels in the supervised learning model of the proposed system.

### **1.2.1 Union-based SQL Injection**

Union-based SQL Injection is one of the most common attack methods. It uses the SQL **UNION** operator to combine the original query with another malicious query.

For example:

| SELECT name, email FROM users UNION SELECT username, password FROM admin; |
| :---- |

If the database allows this operation, sensitive information from another table can be returned to the attacker.

This attack is relatively easy to detect because it usually contains SQL keywords such as **UNION**, **SELECT**, **FROM**, and additional SQL syntax that is uncommon in normal user requests.

### **1.2.2 Error-based SQL Injection**

Error-based SQL Injection forces the database to generate error messages that reveal useful information.

For example, an attacker may intentionally create an invalid SQL statement so that the database returns:

* Table names
* Database version
* Column names
* Database structure

Although modern web applications often hide database errors, many legacy systems still expose detailed error messages that attackers can exploit.

### **1.2.3 Boolean-based Blind SQL Injection**

Boolean-based Blind SQL Injection is more difficult to detect because the application does not return database errors.

Instead, attackers send many SQL queries that return either **True** or **False**.

For example:

| SELECT * FROM users WHERE id=1 AND SUBSTRING(database(),1,1)='m'; |
| :---- |

If the condition is true, the web page behaves normally.

If the condition is false, the page changes slightly.

By repeating this process many times, attackers can recover database information character by character.

Each SQL statement may appear harmless when viewed independently. However, the attack pattern becomes obvious when many related queries are analyzed together. Recognizing that pattern requires looking across a whole sequence of queries rather than any one query in isolation — a capability outside this report's scope (see Conclusions, Future Work).

### **1.2.4 Time-based Blind SQL Injection**

Time-based Blind SQL Injection is similar to Boolean-based attacks, but the attacker observes response time instead of page content.

A common payload is

| SELECT * FROM users WHERE id=1 AND IF(1=1,SLEEP(5),0); |
| :---- |

If the database delays its response for five seconds, the attacker knows that the injected condition is true.

Time-based attacks are difficult to detect because every SQL statement looks almost normal.

Only the response time and repeated request pattern reveal the attack.

### **1.2.5 Stacked Queries**

Some database management systems allow multiple SQL statements in one request.

For example,

| SELECT * FROM users; DROP TABLE users; |
| :---- |

The first statement performs a normal query, while the second statement deletes the database table.

If stacked queries are accepted by the application, attackers can execute arbitrary SQL commands.

Fortunately, these attacks usually contain special symbols such as semicolons and multiple SQL keywords, making them easier for supervised classifiers to recognize.

### **1.2.6 Out-of-band SQL Injection**

Out-of-band (OOB) SQL Injection is a more advanced attack.

Instead of returning results through the normal web response, attackers force the database to communicate with an external server.

Examples include:

* DNS requests
* HTTP requests
* SMB requests

Since these communications happen outside the web application, they cannot always be detected by SQL query analysis alone.

Therefore, OOB SQL Injection is considered outside the scope of this project.

## **1.3 Traditional SQL Injection Detection Methods**

Before Artificial Intelligence became popular, SQL Injection detection mainly depended on manually designed security rules.

### **1.3.1 Input Validation**

Input validation checks whether user input satisfies predefined rules.

Examples include:

* Allow only numbers.
* Reject special characters.
* Limit input length.
* Block dangerous SQL keywords.

Although simple and efficient, input validation cannot prevent every SQL Injection attack because attackers continuously invent new payload variations.

### **1.3.2 Parameterized Queries**

Parameterized queries separate SQL commands from user input.

Instead of building SQL statements by string concatenation, parameters are passed safely to the database.

For example,

Unsafe query:

| SELECT * FROM users WHERE username='" + username + "'"; |
| :---- |

Safe query:

| SELECT * FROM users WHERE username=?; |
| :---- |

Parameterized queries are one of the best methods to prevent SQL Injection.

However, many existing applications still contain vulnerable legacy code.

Therefore, detection systems remain necessary.

### **1.3.3 Rule-based Web Application Firewall**

A Web Application Firewall (WAF) monitors HTTP requests before they reach the web server.

Popular WAF solutions include:

* ModSecurity
* OWASP Core Rule Set (CRS)
* Cloudflare WAF

These systems compare incoming requests against thousands of predefined security rules.

For example, a request containing

| UNION SELECT |
| :---- |

may immediately be blocked.

Rule-based WAFs have several advantages.

* Fast execution
* Easy to understand
* Low computational cost
* High detection rate for known attacks

However, they also have several disadvantages.

* Unable to detect new attack patterns.
* Require frequent manual updates.
* High False Positive Rate.
* Easily bypassed using payload obfuscation.

Because of these limitations, many researchers have started using Artificial Intelligence to improve SQL Injection detection.

## **1.4 Machine Learning for SQL Injection Detection**

Machine Learning allows computers to learn patterns directly from data instead of relying only on manually written rules.

A typical machine learning workflow contains the following steps:

1. Data collection
2. Data preprocessing
3. Feature extraction
4. Model training
5. Model evaluation
6. Prediction

In SQL Injection detection, SQL queries are first converted into numerical feature vectors.

Common feature extraction techniques include:

* Bag of Words
* TF-IDF
* Character n-grams
* Word n-grams

After feature extraction, classifiers such as Logistic Regression, Support Vector Machine (SVM), Random Forest, and XGBoost can be trained.

Compared with rule-based detection, machine learning provides several advantages:

* Better generalization.
* Higher detection accuracy.
* Better adaptability.
* Reduced manual rule creation.

However, traditional machine learning still depends heavily on handcrafted features. Poor feature engineering often leads to poor model performance.

This limitation motivates the use of deep learning models, which can automatically learn feature representations from raw SQL queries.

## **1.5 Deep Learning for SQL Injection Detection**

In recent years, deep learning has become one of the most popular approaches for cybersecurity tasks. Unlike traditional machine learning, deep learning models can automatically learn useful features from raw input data without requiring manual feature engineering.

For SQL Injection detection, deep learning models learn the semantic relationships between SQL keywords, operators, identifiers, and special symbols. As a result, they usually achieve better performance than traditional machine learning models when enough training data is available.

The most common deep learning models used in SQL Injection detection include Convolutional Neural Networks (CNN), Recurrent Neural Networks (RNN), Long Short-Term Memory (LSTM), Gated Recurrent Unit (GRU), and Transformer-based models.

Compared with traditional methods, deep learning provides several advantages.

* Automatic feature extraction.
* Better ability to learn complex attack patterns.
* Higher detection accuracy.
* Better generalization on unseen data.

However, deep learning models also have several disadvantages.

* Require more training data.
* Require more computational resources.
* Longer training time.
* More difficult to explain prediction results.

Therefore, selecting an appropriate deep learning model is an important step in designing an AI-based SQL Injection detection system.

### **1.5.1 Convolutional Neural Networks (CNN)**

Convolutional Neural Networks were originally developed for image processing. However, they have also shown good performance in text classification tasks.

For SQL Injection detection, SQL queries are converted into token sequences before being processed by the CNN model. The convolution layers automatically identify important local patterns such as SQL keywords, operators, comments, and suspicious character combinations.

Figure 1.1 illustrates the general CNN workflow.

![][image1]

Compared with RNN models, CNN offers several advantages.

* Faster training.
* Lower computational cost.
* Good feature extraction capability.
* Easy to deploy.

Because SQL queries are usually short, CNN can effectively learn local attack patterns while maintaining low inference latency. CNN is one of the four architectures empirically compared for Branch 1 in this report (Section 2.8).

### **1.5.2 Recurrent Neural Networks (RNN)**

Recurrent Neural Networks are designed to process sequential data.

Unlike CNN, an RNN processes one token at a time while maintaining information from previous tokens.

This characteristic allows RNNs to understand the order of SQL keywords.

For example, the following two SQL statements contain similar words but have different meanings.

| SELECT * FROM users DROP TABLE users |
| :---- |

The sequential information helps RNN distinguish between normal database operations and malicious SQL commands.

However, standard RNN suffers from the vanishing gradient problem when processing long sequences.

Therefore, LSTM and GRU were introduced to improve sequence learning.

### **1.5.3 Long Short-Term Memory (LSTM)**

Long Short-Term Memory (LSTM) is an improved version of RNN.

LSTM introduces memory cells and gating mechanisms that allow important information to be retained for a longer period.

This makes LSTM suitable for processing long text sequences.

For SQL Injection detection, LSTM can learn relationships between SQL keywords appearing far apart in the same query.

Advantages of LSTM include

* Better long-term memory.
* Higher detection accuracy.
* Better sequence modeling.

Disadvantages include

* Slower training.
* Higher memory usage.
* Longer inference time.

Although LSTM performs well, many recent studies prefer Transformer-based models because they provide better parallel processing capability.

### **1.5.4 Gated Recurrent Unit (GRU)**

GRU is another improvement over standard RNN.

Compared with LSTM, GRU contains fewer gates and fewer parameters.

Therefore, GRU usually trains faster while maintaining similar performance.

Compared with LSTM, GRU provides

* Faster inference.
* Smaller model size.
* Lower memory consumption.
* Good sequence learning performance.

These characteristics make GRU a candidate worth revisiting for sequence-oriented detection work beyond this report's current scope (see Conclusions, Future Work).

## **1.6 Transformer-based Models**

Transformer architecture has become the dominant approach in Natural Language Processing (NLP).

Unlike RNN, Transformer processes all tokens simultaneously using the Self-Attention mechanism.

Self-Attention allows the model to identify important relationships between different parts of a sentence regardless of their positions.

Because SQL statements also have grammatical structures similar to natural language, Transformer models can effectively understand SQL syntax.

Popular Transformer models include

* BERT
* RoBERTa
* ALBERT
* DistilBERT

Among these models, DistilBERT is widely used because it provides a good balance between accuracy and computational cost.

### **1.6.1 DistilBERT**

DistilBERT is a compressed version of BERT.

It contains fewer parameters while preserving most of BERT's language understanding capability.

Compared with the original BERT model, DistilBERT provides

* Smaller model size.
* Faster inference.
* Lower memory usage.
* Similar prediction accuracy.

Because this project focuses on real-time SQL Injection detection, DistilBERT is selected as one of the candidate models for the supervised learning branch.

This project's implementation empirically compares DistilBERT against three lighter alternatives (TF-IDF + Logistic Regression, TF-IDF + LightGBM, and a lightweight CNN with a SQL-specific tokenizer) and selects the final model for the supervised classification branch based on the F1-macro / latency / model-size trade-off (see Section 2.8).

### **1.6.2 Why Not Use Large Language Models?**

Recently, Large Language Models (LLMs) such as GPT have achieved excellent performance in many NLP tasks.

However, deploying LLMs inside a real-time database proxy presents several challenges.

First, LLMs require large computational resources.

Second, inference latency is much higher than lightweight Transformer models.

Third, deployment cost is significantly higher.

Finally, real-time SQL query filtering requires predictions within only a few milliseconds.

Therefore, lightweight models such as DistilBERT or CNN are more suitable for this project.

## **1.7 Anomaly Detection**

Most supervised learning models require labeled attack data.

However, new SQL Injection techniques appear continuously.

Collecting labeled samples for every new attack is almost impossible.

To solve this problem, anomaly detection is introduced as the second detection branch.

Instead of learning malicious behavior, anomaly detection learns only normal database traffic.

When a new SQL query is significantly different from normal behavior, it is considered suspicious.

This approach provides the ability to detect unknown attacks.

Figure 1.2 illustrates the general anomaly detection workflow.

![][image2]

Unlike supervised learning, anomaly detection produces a continuous anomaly score instead of a class label.

### **1.7.1 Isolation Forest**

Isolation Forest is one of the most popular anomaly detection algorithms.

The main idea is simple.

Abnormal samples are easier to isolate than normal samples.

The algorithm constructs many random decision trees.

Queries that require fewer splits to isolate are considered anomalies.

Advantages include

* Fast training.
* Low memory usage.
* Suitable for high-dimensional data.
* Good scalability.

Isolation Forest is one of the two algorithms empirically compared for Branch 2 in this report (Section 2.9).

### **1.7.2 One-Class SVM**

One-Class Support Vector Machine is another anomaly detection algorithm.

Instead of separating two classes, One-Class SVM learns the boundary surrounding only normal data.

Queries outside this boundary are classified as anomalies.

Although One-Class SVM provides good detection accuracy, it usually requires careful parameter tuning and has higher computational complexity than Isolation Forest. Section 2.9 reports the empirical comparison between the two for this project's data.

### **1.7.3 Role of Anomaly Detection in This Project**

In the proposed system, anomaly detection does not replace supervised classification.

Instead, it complements the supervised classifier (Branch 1).

For this midterm report, the anomaly score serves one purpose: identifying previously unseen SQL Injection attacks that Branch 1 was not trained to recognize. The longer-term design also intends to feed this score into session-level analysis; that use is not implemented and is discussed only as future work (Conclusions).

This design allows the system to analyze not only the content of each SQL query but also its statistical abnormality, improving overall detection capability while maintaining acceptable computational cost.

## **1.8 Hybrid Detection**

A single detection method cannot identify every type of SQL Injection attack. Supervised learning performs well on known attacks but may fail when attackers use new payloads. On the other hand, anomaly detection can identify unusual behavior, but it usually produces a higher False Positive Rate because not every unusual query is malicious.

To overcome these limitations, this project combines two detection methods into one hybrid architecture.

* **Branch 1:** Supervised SQL Injection Classification
* **Branch 2:** Query-level Anomaly Detection

Each branch focuses on a different aspect of SQL Injection detection. The supervised model identifies known attack patterns. The anomaly detector identifies previously unseen behavior. Both predictions are combined by a decision rule.

This two-branch architecture improves detection accuracy while reducing the weaknesses of either method alone.

### **1.8.1 Two-Branch Detection Architecture**

The proposed system places an AI proxy between the web application and the database server. Every SQL statement passes through this proxy before reaching the database.

The workflow can be summarized as follows.

1. The web application generates a SQL query.
2. The Database Proxy receives the SQL statement.
3. The SQL statement is normalized through the canonicalization process.
4. Branch 1 predicts whether the query belongs to a known SQL Injection category.
5. Branch 2 calculates an anomaly score.
6. The Decision Engine combines the outputs.
7. The system decides to allow, block, or hold the request.

In this report, the supervised classification component (Branch 1) and the query-level anomaly detection component (Branch 2) have been implemented and evaluated on real data (Section 2.8–2.9). The full multi-step Decision Engine sketched above has not yet been implemented as a running system (Section 2.6); it is discussed as future work (Conclusions).

### **1.8.2 Overkill Policy**

Instead of making only two decisions (Allow or Block), the proposed system introduces an additional security policy called **Overkill**.

The purpose of Overkill is to reduce the risk of missing dangerous attacks.

The decision rules are summarized below.

| Branch 1 | Branch 2 | System Action |
| :---- | :---- | :---- |
| Attack | \- | Block immediately |
| Normal | Abnormal | Hold for administrator verification |
| Normal | Normal | Allow request |

The **Hold** action is an important feature because it allows administrators to verify suspicious queries before they are executed.

Although this policy may slightly increase response time, it significantly improves system security. As with the rest of the Decision Engine, Overkill is a design described here and evaluated only conceptually (Section 2.6); no administrator-review workflow has been built.

## **1.9 Related Work**

Many researchers have proposed Artificial Intelligence methods for SQL Injection detection [1]. Rather than re-explaining how each technique works — already covered in Sections 1.4–1.8 — this section summarizes what published studies actually applied, and what they consistently miss.

On the supervised side, classical machine learning pipelines (TF-IDF/n-gram features with SVM, Random Forest, and XGBoost) remain common because they are fast and cheap to deploy [2]; CNN-based classifiers are used where automatic feature extraction from raw query text is preferred [3]; and sequence models (LSTM/GRU) or their ensembles are applied when the goal extends to broader web-attack detection, not SQLi alone [4]. Transformer-based approaches — including SQLi-specific fine-tuned or hybrid BERT variants [7, 8], built on the general DistilBERT compression technique [6] — are increasingly reported, trading model size and inference latency for contextual accuracy.

On the unsupervised side, anomaly detection built on Isolation Forest [9] or One-Class SVM [10] is used specifically to catch attacks a supervised model was never trained on, at the cost of a higher false-positive rate than a well-tuned classifier alone.

A separate line of work studies how easily these detectors can be evaded rather than how well they classify: adversarial mutation tools such as WAF-A-MoLE [11] generate semantically-equivalent payload variants specifically to bypass ML-based WAFs — this is part of why Section 2.12.5 treats this report's F1/AUC figures as an upper bound, not a robustness guarantee.

Separately from technique choice, some intrusion-detection research also explores Continual Learning — updating a deployed model from new data without full retraining — as a way to keep pace with new attack variants; that direction is discussed further in Section 1.10.4 and is not implemented in this project (Conclusions, Future Work).

Across nearly all of the work above — supervised, anomaly-based, or hybrid — the prediction is made from a single query in isolation. Very few studies model the relationship between multiple queries generated in the same session, which is exactly the gap Section 1.10 develops.

### **Table 1.1 Comparison of Existing Detection Methods**

| Method | Advantages | Limitations | Ref. |
| :---- | :---- | :---- | :---- |
| Rule-based WAF | Fast, simple, easy to deploy | Cannot detect new attacks | — |
| Machine Learning (SVM/RF/XGBoost) | Lightweight, good accuracy | Requires feature engineering | [2] |
| CNN | Automatic feature extraction | Needs labeled data | [3] |
| LSTM / GRU | Learns sequential information | Higher computational cost | [4] |
| Transformer / DistilBERT | High accuracy, understands context | Larger model size | [6, 7, 8] |
| Anomaly Detection | Detects unknown attacks | Higher False Positive Rate | [9, 10] |
| Hybrid Detection | Combines multiple strengths | More complex implementation | [7] |

From this comparison, it can be seen that no single method can solve every problem.

Therefore, combining multiple detection approaches is a reasonable solution.

## **1.10 Research Gap**

After reviewing previous studies, several research gaps can be identified. These describe gaps in the *published literature*, not claims about what this project has already built — that distinction matters for 1.10.5 below.

### **1.10.1 Query-Level Detection Only**

Most AI-based SQL Injection detection systems treat every SQL query as an independent sample.

The model predicts whether a single SQL statement is malicious without considering previous user activities.

This assumption works well for traditional SQL Injection attacks but becomes ineffective against multi-step attacks.

### **1.10.2 Difficulty Detecting Blind SQL Injection**

Blind SQL Injection usually consists of hundreds of SQL queries.

Each individual query appears harmless.

Only after observing the complete sequence does the attack pattern become obvious.

Therefore, single-query classifiers cannot effectively detect this attack.

### **1.10.3 Lack of Session-Level Analysis**

Most previous studies do not analyze SQL queries at the session level.

They ignore information such as

* query order,
* execution frequency,
* repeated access patterns,
* user behavior.

These characteristics are important for detecting advanced SQL Injection attacks.

### **1.10.4 Limited Adaptability**

Many published models remain static after deployment.

When attackers create new SQL Injection techniques, detection performance gradually decreases.

Few systems include a practical Continual Learning pipeline for updating models using administrator feedback.

### **1.10.5 What This Report Contributes**

Based on the identified research gaps, the full project (of which this report covers a part) is designed to eventually address all four gaps above. **For this midterm report specifically**, the contribution is narrower and empirical: a working, evaluated supervised classifier (Branch 1) combined with a working, evaluated query-level anomaly detector (Branch 2), built on a combined and carefully cleaned public dataset, with measured — not assumed — results (Chapter 2).

Addressing 1.10.1–1.10.3 (query-level-only detection, Blind SQLi, session-level analysis) via a session-aware architecture, and 1.10.4 (limited adaptability) via a Continual Learning loop, remain designed but unimplemented parts of the project; they are stated explicitly as future work in the Conclusions, not claimed here.

---

# **CHAPTER 2. EXPERIMENTAL RESULTS**

*(Per the report template, this single chapter covers system design, data, methodology, results, and discussion as subsections — all findings below are for Branch 1 and Branch 2 only.)*

## **2.1 System Placement: The Database Proxy**

The proposed detection system is placed at the Database Proxy layer, between the web application backend and the database server. This placement — referred to internally as "Position B" — is a deliberate design choice: the proxy only observes a SQL statement **after** the backend has already assembled it from user input, and **before** it reaches the database engine.

This placement has two direct consequences for the threat model. First, it neutralizes horizontal query splitting (an attacker spreading a single payload across multiple request parameters), because the proxy only ever sees the final, concatenated SQL string — it does not need to reconstruct the query from separate parameters the way an input-layer WAF would. Second, it means the system cannot see anything upstream of query construction (raw HTTP parameters, headers) or downstream of query execution (result sets, out-of-band channels), which bounds the scope described in the Scope of the Study section and in Section 2.12.4 below.

*(Figure recommended here, not yet created: a diagram of this placement and the request flow through Branch 1 / Branch 2 — see List of Figures.)*

## **2.2 Canonicalization**

Before either branch processes a query, the raw SQL string passes through a canonicalization step that normalizes superficial syntactic variation (whitespace, letter case, comment style, equivalent literal encodings) so that the downstream models operate on a consistent representation. Canonicalization is shared across both branches and is the first line of defense against simple obfuscation; it does not, by itself, defend against the semantic-level evasion strategies discussed in Section 2.12.5.

## **2.3 Data Sources**

Four public datasets were used, combined differently for Branch 1 and Branch 2:

* **SQLiV3** — a Kaggle-distributed SQL Injection query collection. License provenance is unclear (see Section 2.12.2) and this is treated as an open limitation.
* **CSIC 2010** — the well-known HTTP CSIC 2010 dataset, used both as a source of clean benign traffic (via its session cookies) and, held out separately, as a labeled anomalous evaluation set for Branch 2.
* **payload-box** — a curated, MIT-licensed collection of SQL Injection payload strings, used to enrich the attack side of the Branch 1 dataset.
* **SR-BH 2020** — a honeypot dataset (Harvard Dataverse, CC0 1.0), 527,813 rows, of which 250,285 carry an original `SQL Injection` tag. Because the original labels are coarse and multi-attack (CAPEC-tagged), rows were re-tagged by rule-based sub-type matching rather than trusted as-is.

## **2.4 Branch 1 — Supervised Multi-Class Classification: Methodology and Dataset**

Branch 1 classifies each canonicalized query into one of five classes: `normal`, `union_based`, `error_based`, `boolean_blind`, and `time_blind` (see below for why a sixth class, `stacked`, was excluded from training). Four candidate architectures were implemented and compared under identical train/test conditions: TF-IDF features with Logistic Regression, TF-IDF features with LightGBM, a fine-tuned DistilBERT, and a lightweight CNN with a SQL-specific tokenizer. The comparison criterion was **F1-macro**, not accuracy, because the underlying class distribution is imbalanced; latency (p50, measured per single query) and on-disk model size were tracked as secondary, deployment-relevant criteria. The selected model and the full comparison are reported in Section 2.8.

**Sub-type re-labeling of SR-BH 2020** contributed the majority of usable per-class volume: +83,189 `union_based`, +7,423 `error_based`, +126,926 `boolean_blind`, +32,747 `time_blind`.

**The `stacked` class had zero naturally-occurring samples** across SQLiV3, payload-box, and SR-BH 2020 combined, under both strict and loose regex matching. To keep the class representable at all, 363 synthetic samples were generated by templating 11 statement prefixes × 11 destructive/privilege-escalation payloads × 3 comment-style suffixes, tagged with a distinct `synthetic_stacked` provenance flag. During architecture comparison, all four candidate models achieved 100% recall on this class — a sign that the synthetic templates are trivially separable rather than a genuine quality signal — so `stacked` was **excluded from the training set actually used for the reported results** (Section 2.8), while the generation code was kept for reuse once real stacked-query traffic becomes available.

**Label-noise cleaning on the `normal` side.** Cross-checking SR-BH 2020's own multi-label flags at the aggregate level looked reassuring (99.1% of `SQL Injection=1` rows carried no contradicting flag; 0% of `Normal=1` rows had a contradicting flag), but manual reading of individual rows labeled `Normal=1` found real attacks mislabeled as benign — e.g. a genuine time-based blind payload (`sleep(15)`) and a Shellshock payload (`() {{ :;}}; /bin/sleep 15`) that did not trip any of SR-BH 2020's own contradiction flags. This shows that cross-checking label flags alone is insufficient; content has to be read. A content-based signature filter (independent of the source label) was applied to every row destined for `normal`, and iterated over three rounds as new evasive variants kept surfacing on manual inspection — an alternate-separator command injection (`&cat /etc/passwd&`), an SSI injection variant, and a fuzzer-style evasion that inserted junk tokens between keywords (`cat$jj $jj/etc$jj/passwd`). The decision was made to stop iterating the filter at that point — evasion-variant discovery is open-ended, and the appropriate long-term fix is canonicalization plus an adversarial test set (Section 2.12.5), not indefinite dataset patching. In total, 2,892 rows were removed from the `normal` candidate pool on this basis (~9.8% at the point measured, later extended when an XSS signature group was added).

**A parallel noise check on `boolean_blind`** — the "catch-all" class for payloads not matching the other four explicit rules — found that a manual review of 30 samples contained 4 clear mislabels (~13%): SSRF payloads, CRLF/header injection, and one entirely benign row. This figure is reported as a measured quantity, not an estimate, and is carried into Section 2.12.1.

**Final dataset:** 68,159 rows across the five real classes plus the 363 synthetic `stacked` rows; with `stacked` excluded from training, the dataset actually used is 67,796 rows, split 54,236 train / 13,560 test (stratified, seed = 42). The three largest classes (`union_based`, `boolean_blind`, `time_blind`) were undersampled to roughly 15,000 rows each; `error_based` was kept at its full size (~7,796 rows, insufficient to undersample without losing statistical power). F1-macro is used as the primary Branch 1 metric because accuracy would be distorted by the original class imbalance.

## **2.5 Branch 2 — Query-Level Anomaly Detection: Methodology and Dataset**

Branch 2 is trained exclusively on benign traffic and produces a continuous anomaly score for each query, rather than a class label. Because the goal is to generalize to attack syntax that has never been observed, Branch 2 deliberately avoids TF-IDF (which is tied to vocabulary seen during training) and instead uses four generic statistical/structural features computed directly from the canonicalized query string: length, ratio of special characters, count of SQL keywords, and Shannon entropy. Two unsupervised algorithms were compared — Isolation Forest and One-Class SVM — under the same feature set and preprocessing (Section 2.9).

Branch 2 pools clean benign rows from SQLiV3, CSIC 2010, and SR-BH 2020, using the same content-based filtering described in Section 2.4 to reject rows resembling any known attack category (SQLi and, incidentally, OS command injection, SSI, and XSS) rather than only SQLi — a broader filter than Branch 1 needs, because an anomaly detector's training pool has to be clean of *any* abnormal traffic, not just SQLi. After filtering (~7.4% of candidates rejected) and de-duplication (roughly 113,000 duplicate rows removed, largely repeated static-asset requests present in CSIC 2010/SR-BH 2020), the benign pool contains 91,935 rows (73,548 train / 18,387 test). The four statistical features above are pre-computed as columns on this dataset.

A separate, held-out set of 25,065 anomalous rows from CSIC 2010 is kept exclusively for evaluation (never used in training) to measure false-positive rate and detection rate. This set is not SQLi-exclusive — it mixes multiple CSIC 2010 attack categories (buffer overflow, XSS, path traversal, in addition to SQLi) — so its average `sql_keyword_count` is, counter-intuitively, *lower* than the benign pool's (0.13 vs. 0.35). Results on this set (Section 2.9) should therefore be read as "general anomaly detection rate," not a SQLi-specific detection rate, unless the SQLi subset is isolated separately.

For the model reported in Section 2.9, the One-Class SVM was fit on a 12,000-row sample of the benign training pool rather than the full 73,548 rows; this reflects the practical scaling limits of One-Class SVM on the available hardware and is noted here as an open methodological point worth revisiting (Section 2.12.6) rather than glossed over.

## **2.6 Decision Rule and the Overkill Policy (Midterm Scope)**

The full project design combines the outputs of Branch 1, Branch 2, and (eventually) a session-level component through a central Decision Engine. **Only the Branch 1 + Branch 2 portion below has any empirical grounding in this report** — and even that is per-branch evaluation (Section 2.8–2.9), not an integrated, running decision service. Table 2.1 shows this two-branch decision rule.

### **Table 2.1 Decision Table (Two-Branch Design, Midterm Scope)**

| Branch 1 | Branch 2 | System Action |
| :---- | :---- | :---- |
| Attack | — | Block immediately, log the request |
| Normal | Abnormal | HOLD for administrator verification (Overkill) |
| Normal | Normal | Allow |

The **Overkill** policy — holding a request rather than forcing an immediate allow/block decision — is intended to reduce the cost of a wrong decision at the expense of added latency and administrator workload. A fail-safe rule (deny-by-default on decision-engine timeout or failure) is part of the design but has not been implemented as a running system.

## **2.7 Evaluation Protocol**

Branch 1 is evaluated with per-class Precision/Recall/F1, F1-macro as the headline metric, a confusion matrix, and per-class ROC curves. Branch 2 is evaluated with false-positive rate and detection rate at a fixed operating threshold, AUC, a Precision-Recall curve (average precision), and a threshold sweep (21 threshold points, trading off FPR against detection rate and precision) to support a deployment-time threshold choice. Both branches report p50 inference latency and on-disk model size as deployment-relevant secondary metrics; the actual runtime environment (CPU/GPU used for latency measurement) should be stated alongside these numbers in the final camera-ready figures.

## **2.8 Branch 1 Results**

Table 2.2 reports the four-architecture comparison (6-class data, including `stacked`, at comparison time).

### **Table 2.2 Branch 1 Architecture Comparison**

| Model | F1-macro | p50 latency | Model size | Train time |
| :---- | :---- | :---- | :---- | :---- |
| **TF-IDF + Logistic Regression (chosen)** | 0.985 | 0.5 ms | 3.9 MB | 10 s |
| TF-IDF + LightGBM | 0.993 | 60 ms | 6.0 MB | 264 s |
| DistilBERT | 0.992 | 2.8 ms (GPU) | 256 MB | 1,443 s |
| CNN + SQL-tokenizer | 0.987 | 0.3 ms | 116 KB (28K params) | 10 s |

TF-IDF + Logistic Regression was selected: the F1-macro spread across all four candidates is small (0.985–0.993), while LightGBM is roughly 120× slower per query (60 ms, too high for a real-time proxy) and DistilBERT requires a GPU and 256 MB on disk for no measurable F1 gain over the chosen model. The CNN is the strongest fallback candidate (smallest and fastest) if a future iteration needs stronger learned features than TF-IDF can provide.

After excluding the `stacked` class (Section 2.4) and retraining on the resulting 5-class, 67,796-row dataset, the model reaches **F1-macro = 0.9822**. Table 2.3 gives the per-class breakdown.

### **Table 2.3 Branch 1 Per-Class Results (Test Set, n = 13,560)**

| Class | Precision | Recall | F1 | Support |
| :---- | :---- | :---- | :---- | :---- |
| normal | 0.966 | 0.947 | 0.956 | 3,000 |
| union_based | 0.999 | 0.990 | 0.995 | 3,000 |
| error_based | 0.998 | 1.000 | 0.999 | 1,560 |
| boolean_blind | 0.948 | 0.974 | 0.961 | 3,000 |
| time_blind | 1.000 | 1.000 | 1.000 | 3,000 |

**→ Insert Figure 2.1 here (`report/metrics/figures/nhanh1_roc_per_class.png`) — Branch 1 per-class ROC curves.**

The confusion matrix shows the only material confusion is between `normal` and `boolean_blind` (157 `normal` rows misclassified as `boolean_blind`; 74 `boolean_blind` rows misclassified as `normal`), which is consistent with the ~13% measured label noise found in `boolean_blind` during manual review (Section 2.4). As stated in the evaluation notes, this F1 score should not be read as "near-perfect" performance — it is measured on a clean test split, not on adversarially-perturbed input (Section 2.12.5).

## **2.9 Branch 2 Results**

Table 2.4 compares the two candidate algorithms.

### **Table 2.4 Branch 2 Algorithm Comparison**

| Algorithm | Contamination | FPR | Detection Rate | AUC |
| :---- | :---- | :---- | :---- | :---- |
| Isolation Forest | 0.01 | 0.63% | 3.19% | 0.670 |
| **One-Class SVM (chosen)** | 0.005 | **0.30%** | **20.73%** | **0.902** |

One-Class SVM was selected for its substantially higher AUC and detection rate at a comparable (in fact lower) false-positive rate. On the held-out evaluation (3,000 benign, 25,065 anomalous, mixed-attack-type as noted in Section 2.5), the chosen model produces 9 false positives out of 3,000 benign queries (FPR = 0.3%) and correctly flags 5,196 of 25,065 anomalous queries (detection rate = 20.7%), with average precision (PR-AUC) = 0.982.

**→ Insert Figure 2.2 here (`report/metrics/figures/nhanh2_pr_curve.png`) — Branch 2 Precision–Recall curve.**
**→ Insert Figure 2.3 here (`report/metrics/figures/nhanh2_score_dist.png`) — Branch 2 anomaly score distribution, benign vs. anomalous.**

As noted in Section 2.5, the 20.7% detection rate is measured against a multi-attack-type evaluation set, not a SQLi-only one; it should be read as a general anomaly detection rate unless the evaluation set is first filtered to SQLi-only rows.

**Why a headline detection rate of 20.7% is consistent with AUC = 0.902.** FPR and detection rate are both computed at a *single, fixed* decision threshold — the one corresponding to the deployed operating point (contamination = 0.005). AUC, by contrast, integrates performance across the *entire* range of possible thresholds. A high AUC with a low detection rate at one specific point simply means the model separates benign from anomalous traffic well overall, and the deployed threshold was chosen deliberately conservative (to keep FPR — and therefore the Overkill/HOLD administrator workload, Section 2.6 — very low), not that the model is weak. A full sweep across 21 thresholds (`report/metrics/nhanh2_threshold_sweep.csv`) makes this trade-off explicit; Table 2.5 shows selected points from that sweep.

### **Table 2.5 Branch 2 Threshold Sweep (Selected Operating Points)**

| Operating point | FPR | Detection Rate | Precision |
| :---- | :---- | :---- | :---- |
| **Deployed (contamination = 0.005)** | **0.30%** | **20.7%** | 99.8% |
| Relaxed 1 | 3.17% | 33.2% | 98.9% |
| Relaxed 2 | 13.4% | 65.6% | 97.6% |
| Relaxed 3 | 20.5% | 87.1% | 97.3% |
| Relaxed 4 | 30.6% | 97.1% | 96.4% |
| Maximally relaxed | ~100% | 100% | — |

**→ Insert Figure 2.4 here (`report/metrics/figures/nhanh2_threshold_tradeoff.png`) — FPR / Detection-Rate threshold trade-off.**

Detection rate rises sharply as the threshold is relaxed — reaching 97.1% at 30.6% FPR — which is exactly what a high AUC predicts. The deployed operating point was chosen at the very-low-FPR end of this curve because, under the Overkill policy (Section 2.6), every false positive becomes work for an administrator; the appropriate operating point is therefore a deployment/product decision, not a fixed property of the model, and Table 2.5 (or the full 21-point sweep) is the artifact that should be handed to whoever makes that decision.

## **2.10 Illustrative Demonstration**

A demonstration notebook (`train/notebooks/demo_detect.ipynb`) loads the trained Branch 1 and Branch 2 models, accepts a SQL query as input, and returns a combined verdict. On a small, randomly-sampled set of 20 queries, 19 were classified correctly; the single error is consistent with the known `normal` ↔ `boolean_blind` confusion described in Section 2.8. This notebook is an illustrative, minimal integration and should not be read as a demonstration of the full Decision Engine described in Section 2.6.

## **2.11 Summary of Results**

Branch 1 and Branch 2 both meet the accuracy targets set out in the Research Objectives, at latencies (0.5 ms and — for Branch 2, feature computation plus a linear SVM decision — comparably small) consistent with real-time proxy use. Branch 2's headline detection rate (20.7%) looks low in isolation, but Section 2.9 shows this is a deliberately conservative operating-point choice, not a weak model — AUC = 0.902 and the threshold sweep (Table 2.5) confirm detection rate rises above 97% if a higher FPR is accepted.

## **2.12 Discussion and Limitations**

### **2.12.1 Label Noise**

Two independent, measured sources of label noise were found during data construction rather than assumed: mislabeled `normal` rows in the SR-BH 2020 honeypot data requiring three rounds of content-based filtering (Section 2.4), and ~13% mislabeled samples in the `boolean_blind` catch-all class from a small manual audit (30 samples). Both figures should be reported as measured limitations alongside the F1-macro = 0.9822 result, since they plausibly explain the dominant confusion pattern in Table 2.3 and mean the "true" ceiling for this task, with clean labels, is unknown.

### **2.12.2 Dataset Licensing**

payload-box (MIT) and SR-BH 2020 (CC0 1.0) have confirmed licenses. SQLiV3 does not: its original Kaggle listing carries no explicit license, and a GitHub mirror's self-applied MIT tag does not establish that the mirror actually holds redistribution rights over the underlying data. Until this is resolved, the combined dataset (which includes SQLiV3) should be treated as **provenance-unclear**, not as a cleanly MIT/CC0-licensed release, and this should be stated explicitly before any public dataset release (see also Conclusions, Future Work).

### **2.12.3 Synthetic Data for the `stacked` Class**

No public source among SQLiV3, payload-box, or SR-BH 2020 contains naturally-occurring stacked-query examples. The 363 synthetic samples generated to represent this class are template-based and were found to be trivially separable (100% recall across all four candidate architectures) — a sign of low sample diversity, not of a solved sub-problem. This class was excluded from the reported training run for that reason (Section 2.4) and remains effectively unvalidated by this project.

### **2.12.4 Threat Model Boundaries**

The system's placement at the Database Proxy (Section 2.1) defines clear boundaries. In scope: Union-based, Error-based, Boolean-blind, Time-blind, and Stacked-query SQL Injection. Explicitly out of scope: second-order SQL Injection (a payload stored safely in one request and triggered in a later, unrelated request, potentially days apart); out-of-band SQL Injection (data exfiltrated via DNS/HTTP channels the proxy never observes); and HTTP Parameter Pollution upstream of query construction, which the Position-B placement mitigates as a side effect rather than by design. Multi-step attacks that only reveal themselves across a sequence of queries (e.g., Blind SQLi carried out over many requests) are also outside what Branch 1 and Branch 2 can catch individually — closing that gap is exactly what the future-work session-level component (Conclusions) is intended for. These boundaries were already stated in the Scope of the Study section and are repeated here because they directly bound how the results in this chapter should be generalized.

### **2.12.5 Adversarial Robustness Gap**

All results in this chapter are measured on clean, held-out test splits of the training distribution. No adversarially-perturbed test set (e.g., generated with a tool such as WAF-A-MoLE [11]) has yet been run against either branch. The F1-macro and AUC figures above should therefore be read as an upper bound on current performance, not as evidence of robustness to deliberate evasion — this is listed explicitly as unfinished work in the Conclusions.

### **2.12.6 Methodological Open Points**

Two points are flagged here rather than silently accepted: (1) the Branch 2 One-Class SVM was trained on a 12,000-row subsample of the available 73,548-row benign pool (Section 2.5), and the effect of training on the full pool has not been measured; (2) manual label-noise auditing so far covers small samples (15–30 rows per class) rather than the ~100+/class cross-validated audit that would be needed to fully trust the noise-rate estimates in Section 2.12.1.

---

# **CONCLUSIONS**

## **Summary of Contributions**

This midterm report covers two working, evaluated components of a larger planned SQL Injection detection system: a supervised multi-class classifier (Branch 1, F1-macro = 0.9822) and a query-level anomaly detector (Branch 2, One-Class SVM, AUC = 0.902). Both were trained on a combined and carefully cleaned public dataset and evaluated with measured — not assumed — results, including a documented account of the label-noise issues found along the way (Section 2.12.1).

Everything beyond these two components — session-level detection across multiple queries, an integrated Decision Engine, the Overkill administrator-review workflow, and Continual Learning from administrator feedback — is part of the project's longer-term design (motivated by the research gaps in Section 1.10) but has **not** been implemented or evaluated. It is listed below as future work, not claimed as a current contribution.

## **Future Work**

The following items are known, scoped gaps rather than open-ended possibilities:

1. **Integrated system** (Database Proxy API, Decision Engine, administrator interface). Design exists (Section 2.6); no running integration beyond the illustrative demonstration notebook (Section 2.10).
2. **Session-level sequence detection**, end to end. No lab, no session data, no trained model — this is the largest remaining gap relative to the project's original motivation (Section 1.2.3, Section 1.10.3).
3. **Continual Learning loop**, connecting administrator feedback on held requests to periodic retraining with a validation gate.
4. **Concept drift monitoring in production** — periodic tracking of FPR/recall over time, model versioning and rollback.
5. **A production-grade Session Store** (TTL/eviction policy, and a shared backend such as Redis if the proxy runs as multiple instances) — a prerequisite for session-level detection.
6. **Latency/throughput benchmarking under realistic load** — current results measure correctness, not sustained throughput.
7. **Multi-round adversarial hardening** (iterated generate–test–retrain cycles against a tool such as WAF-A-MoLE) for Branch 1 and Branch 2.
8. **Larger-scale, cross-validated manual label auditing** (~100+ samples per class) to firm up the noise-rate estimates in Section 2.12.1.
9. **Resolving dataset licensing** before any public dataset release (Section 2.12.2).
10. **Broader comparison against published SOTA baselines**, appropriate for an extended (journal-length) version of this work.

---

# **REFERENCES**

1. A. Paul, V. Sharma, and O. Olukoya, "SQL injection attack: Detection, prioritization & prevention," *Journal of Information Security and Applications*, vol. 85, 2024, Art. no. 103871. DOI: 10.1016/j.jisa.2024.103871.
2. A. E. Widodo and F. F. D. Imaniawan, "Detection of SQL Injection, XSS, and Command Injection Attacks in Web Payloads Using SVM, Random Forest, and XGBoost," *Journal of Information Systems and Informatics*, vol. 8, no. 3, 2026. DOI: 10.63158/journalisi.v8i3.1655.
3. A. Luo, W. Huang, and W. Fan, "A CNN-based Approach to the Detection of SQL Injection Attacks," in *Proc. 2019 IEEE/ACIS 18th Int. Conf. on Computer and Information Science (ICIS)*, 2019. DOI: 10.1109/icis46139.2019.8940196.
4. V. Babaey and H. R. Faragardi, "Detecting Zero-Day Web Attacks with an Ensemble of LSTM, GRU, and Stacked Autoencoders," *Computers*, vol. 14, no. 6, Art. no. 205, 2025. DOI: 10.3390/computers14060205.
5. A. Vaswani, N. Shazeer, N. Parmar, J. Uszkoreit, L. Jones, A. N. Gomez, Ł. Kaiser, and I. Polosukhin, "Attention Is All You Need," in *Advances in Neural Information Processing Systems 30 (NeurIPS 2017)*, 2017. arXiv:1706.03762.
6. V. Sanh, L. Debut, J. Chaumond, and T. Wolf, "DistilBERT, a distilled version of BERT: smaller, faster, cheaper and lighter," 2019. arXiv:1910.01108.
7. Y. Liu and Y. Dai, "Deep Learning in Cybersecurity: A Hybrid BERT–LSTM Network for SQL Injection Attack Detection," *IET Information Security*, vol. 2024, Art. no. 5565950. DOI: 10.1049/2024/5565950.
8. D. Lu, J. Fei, and L. Liu, "A Semantic Learning-Based SQL Injection Attack Detection Technology," *Electronics*, vol. 12, no. 6, Art. no. 1344, 2023. DOI: 10.3390/electronics12061344.
9. F. T. Liu, K. M. Ting, and Z.-H. Zhou, "Isolation Forest," in *Proc. 2008 8th IEEE Int. Conf. on Data Mining (ICDM)*, Pisa, Italy, 2008, pp. 413–422. DOI: 10.1109/ICDM.2008.17.
10. B. Schölkopf, J. C. Platt, J. Shawe-Taylor, A. J. Smola, and R. C. Williamson, "Estimating the Support of a High-Dimensional Distribution," *Neural Computation*, vol. 13, no. 7, pp. 1443–1471, 2001.
11. L. Demetrio, A. Valenza, G. Costa, and G. Lagorio, "WAF-A-MoLE: Evading Web Application Firewalls through Adversarial Machine Learning," in *Proc. 35th Annual ACM Symposium on Applied Computing (SAC '20)*, 2020. arXiv:2001.01952.

*(These 11 references were located via web search to match the topics discussed in Chapter 1 and Section 2.12 — they are not necessarily the same sources the team's original "Khảo sát công trình liên quan" document used, since that file could not be found in this repository. Cross-check against the team's actual survey before finalizing, and replace any entry that doesn't match what was actually read.)*

[image1]: <data:image/png;base64,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>

[image2]: <data:image/png;base64,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>
