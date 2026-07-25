**CONTENTS**

**LIST OF ABBREVIATIONS**	3

**LIST OF TABLES**	4

**LIST OF FIGURES**	5

**INTRODUCTION**	6

Background	6

Research Objectives	7

Scope of the Study	7

Research Methodology	7

**CHAPTER 1\. THEORY**	9

1.1 Overview of SQL Injection	9

1.2 Types of SQL Injection	9

1.2.1 Union-based SQL Injection	9

1.2.2 Error-based SQL Injection	10

1.2.3 Boolean-based Blind SQL Injection	10

1.2.4 Time-based Blind SQL Injection	11

1.2.5 Stacked Queries	11

1.2.6 Out-of-band SQL Injection	11

1.3 Traditional SQL Injection Detection Methods	12

1.3.1 Input Validation	12

1.3.2 Parameterized Queries	12

1.3.3 Rule-based Web Application Firewall	13

1.4 Machine Learning for SQL Injection Detection	14

1.5 Deep Learning for SQL Injection Detection	15

1.5.1 Convolutional Neural Networks (CNN)	16

1.5.2 Recurrent Neural Networks (RNN)	16

1.5.3 Long Short-Term Memory (LSTM)	17

1.5.4 Gated Recurrent Unit (GRU)	17

1.6 Transformer-based Models	18

1.6.1 DistilBERT	18

1.6.2 Why Not Use Large Language Models?	19

1.7 Anomaly Detection	20

1.7.1 Isolation Forest	20

1.7.2 One-Class SVM	21

1.7.3 Role of Anomaly Detection in This Project	21

1.8 Hybrid Detection	22

1.8.1 Two-Branch Detection Architecture	22

1.8.2 Overkill Policy	23

1.9 Related Work	23

1.10 Research Gap	25

1.10.1 Query-Level Detection Only	25

1.10.2 Difficulty Detecting Blind SQL Injection	25

1.10.3 Lack of Session-Level Analysis	25

1.10.4 Limited Adaptability	26

1.10.5 What This Report Contributes	26

**CHAPTER 2\. EXPERIMENTAL RESULTS**	27

2.1 System Placement: The Database Proxy	27

2.2 Canonicalization	27

2.3 Data Sources	28

2.4 Branch 1 — Supervised Multi-Class Classification: Methodology and Dataset	28

2.5 Branch 2 — Query-Level Anomaly Detection: Methodology and Dataset	30

2.6 Decision Rule and the Overkill Policy (Midterm Scope)	31

2.7 Evaluation Protocol	32

2.8 Branch 1 Results	32

2.9 Branch 2 Results	33

2.10 Illustrative Demonstration	36

2.11 Summary of Results	37

2.12 Discussion and Limitations	37

2.12.1 Label Noise	37

2.12.2 Dataset Licensing	37

2.12.3 Synthetic Data for the stacked Class	38

2.12.4 Threat Model Boundaries	38

2.12.5 Adversarial Robustness Gap	38

2.12.6 Methodological Open Points	39

**CONCLUSIONS**	40

Summary of Contributions	40

Future Work	40

**REFERENCES**	42

# **LIST OF ABBREVIATIONS**

| Abbreviation | Meaning |
| ----- | ----- |
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

# **LIST OF TABLES**

Table 1.1  Comparison of Existing Detection Methods	24

Table 2.1  Decision Table (Two-Branch Design, Midterm Scope)	31

Table 2.2  Branch 1 Architecture Comparison	32

Table 2.3  Branch 1 Per-Class Results (Test Set, n \= 13,560)	32

Table 2.4  Branch 2 Algorithm Comparison	34

Table 2.5  Branch 2 Threshold Sweep (Selected Operating Points)	35

# **LIST OF FIGURES**

Figure 1.1  General CNN workflow for SQLi detection (generic/illustrative)	16

Figure 1.2  General anomaly detection workflow (generic/illustrative)	20

Figure 2.1  Branch 1 — per-class ROC curves	33

Figure 2.2  Branch 2 — Precision–Recall curve (OCSVM)	34

Figure 2.3  Branch 2 — anomaly score distribution, benign vs. anomalous	35

Figure 2.4  Branch 2 — FPR/Detection-Rate threshold trade-off	36

# **INTRODUCTION**

## **Background**

With the rapid growth of web applications, protecting databases has become one of the most important tasks in cybersecurity. Modern websites store a large amount of sensitive information such as personal data, passwords, banking information, and business records. Because of this, databases are common targets for attackers.

SQL Injection (SQLi) is one of the oldest and most dangerous web vulnerabilities. It allows attackers to insert malicious SQL commands into user input fields. If the application does not validate user input correctly, these commands can be executed directly by the database management system. As a result, attackers may read confidential information, modify records, delete data, or even gain administrator privileges.

Although many organizations use Web Application Firewalls (WAFs) to protect their systems, traditional rule-based security solutions still have several limitations. They mainly rely on predefined signatures and manually written rules. New attack techniques, obfuscated payloads, and zero-day attacks can bypass these defenses. At the same time, strict rules may incorrectly classify normal queries as malicious, increasing the False Positive Rate (FPR).

Recently, Artificial Intelligence (AI) and Machine Learning (ML) have become promising technologies for cybersecurity. Instead of depending only on predefined rules, AI models can learn attack patterns from historical data and recognize previously unseen attacks. Deep learning models such as CNNs and Transformer-based models have shown high accuracy in many SQL Injection detection studies.

Therefore, this project proposes an AI-Based SQL Injection Detection System**: a supervised classifier for known SQL Injection categories (Branch 1\) and a query-level anomaly detector for previously unseen attack patterns (Branch 2).**

## 

## **Research Objectives**

The main objective of this project is to develop an intelligent SQL Injection detection system using Artificial Intelligence techniques.

•Detect common SQL Injection attacks with high accuracy \- addressed by Branch 1\.

•Detect unknown or zero-day attacks through anomaly detection \- addressed by Branch 2\.

•Reduce False Positive Rate while maintaining fast response time \- addressed by both bran+ches' latency and FPR results.

## **Scope of the Study**

The proposed system focuses on SQL Injection detection at the Database Proxy layer. The proxy receives SQL statements after the backend application has generated the final SQL query but before the query reaches the database server. **This project covers two detection components:**

•Supervised SQL Injection Classification (Branch 1\)

•Query-level Anomaly Detection (Branch 2\)

The following topics are outside the scope of the project entirely:

•Cross-Site Scripting (XSS)

•Cross-Site Request Forgery (CSRF)

•Second-order SQL Injection

•Out-of-band SQL Injection

•Network intrusion detection

•Malware analysis

## 

## **Research Methodology**

This project follows an experimental research methodology. First, datasets containing normal SQL queries and SQL Injection payloads are collected and preprocessed. Second, AI models are trained and evaluated: a supervised multi-class classifier and a benign-only anomaly detector. Third, both detection components are demonstrated together through an illustrative notebook; a fully integrated Database Proxy service is not part of this midterm scope. Finally, both components are evaluated using performance metrics appropriate to each: Precision, Recall, F1-score, and per-class ROC for the classifier; False Positive Rate, Detection Rate, AUC, and a Precision-Recall curve for the anomaly detector; both also report inference latency and model size.

1. # **CHAPTER 1\. THEORY**

## **1.1 Overview of SQL Injection**

SQL Injection is one of the most common web security vulnerabilities. It occurs when user input is directly included in SQL statements without proper validation or parameterization. Normally, a web application receives input from users through forms, search boxes, or URLs. The backend application combines these inputs into SQL statements before sending them to the database. If the application does not sanitize user input correctly, attackers can insert malicious SQL commands.

For example, a normal login query may be written as:

SELECT \* FROM users WHERE username='admin' AND password='123456';

An attacker may enter the following password:

' OR '1'='1

The SQL statement becomes:

SELECT \* FROM users WHERE username='admin' AND password='' OR '1'='1';

Since the condition '1'='1' is always true, the database returns all matching records, allowing unauthorized access.

## **1.2 Types of SQL Injection**

SQL Injection attacks can be divided into several categories depending on how attackers exploit the database. Understanding these attack types is important because they are also used as labels in the supervised learning model of the proposed system.

### ***1.2.1 Union-based SQL Injection***

Union-based SQL Injection is one of the most common attack methods. It uses the SQL **UNION** operator to combine the original query with another malicious query. For example:

SELECT name, email FROM users UNION SELECT username, password FROM admin;

If the database allows this operation, sensitive information from another table can be returned to the attacker. This attack is relatively easy to detect because it usually contains SQL keywords such as **UNION**, **SELECT**, **FROM**, and additional SQL syntax that is uncommon in normal user requests.

### ***1.2.2 Error-based SQL Injection***

Error-based SQL Injection forces the database to generate error messages that reveal useful information. For example, an attacker may intentionally create an invalid SQL statement so that the database returns:

•Table names

•Database version

•Column names

•Database structure

Although modern web applications often hide database errors, many legacy systems still expose detailed error messages that attackers can exploit.

### ***1.2.3 Boolean-based Blind SQL Injection***

Boolean-based Blind SQL Injection is more difficult to detect because the application does not return database errors. Instead, attackers send many SQL queries that return either **True** or **False**. For example:

SELECT \* FROM users WHERE id=1 AND SUBSTRING(database(),1,1)='m';

If the condition is true, the web page behaves normally. If the condition is false, the page changes slightly. By repeating this process many times, attackers  can recover database information character by character. Each SQL statement may appear harmless when viewed independently. However, the attack pattern becomes obvious when many related queries are analyzed together. Recognizing that pattern requires looking across a whole sequence of queries rather than any one query in isolation — a capability outside this report's scope (see Conclusions, Future Work).

### ***1.2.4 Time-based Blind SQL Injection***

Time-based Blind SQL Injection is similar to Boolean-based attacks, but the attacker observes response time instead of page content. A common payload is 

SELECT \* FROM users WHERE id=1 AND IF(1=1,SLEEP(5),0);

If the database delays its response for five seconds, the attacker knows that the injected condition is true. Time-based attacks are difficult to detect because every SQL statement looks almost normal, only the response time and repeated request pattern reveal the attack.

### ***1.2.5 Stacked Queries***

Some database management systems allow multiple SQL statements in one request, for example:

SELECT \* FROM users; DROP TABLE users;

The first statement performs a normal query, while the second statement deletes the database table. If stacked queries are accepted by the application, attackers can execute arbitrary SQL commands. Fortunately, these attacks usually contain special symbols such as semicolons and multiple SQL keywords, making them easier for supervised classifiers to recognize.

### ***1.2.6 Out-of-band SQL Injection***

Out-of-band (OOB) SQL Injection is a more advanced attack. Instead of returning results through the normal web response, attackers force the database to communicate with an external server. Examples include:

* DNS requests  
* HTTP requests  
* SMB requests

Since these communications happen outside the web application, they cannot always be detected by SQL query analysis alone. Therefore, OOB SQL Injection is considered outside the scope of this project.

## **1.3 Traditional SQL Injection Detection Methods**

Before Artificial Intelligence became popular, SQL Injection detection mainly depended on manually designed security rules.

### ***1.3.1 Input Validation***

Input validation checks whether user input satisfies predefined rules, examples include:

* Allow only numbers.   
* Reject special characters.   
* Limit input length.   
* Block dangerous SQL keywords.

Although simple and efficient, input validation cannot prevent every SQL Injection attack because attackers continuously invent new payload variations.

### ***1.3.2 Parameterized Queries***

Parameterized queries separate SQL commands from user input. Instead of building SQL statements by string concatenation, parameters are passed safely to the database. For example, 

Unsafe query:

SELECT \* FROM users WHERE username="' \+ username \+ '";

Safe query:

SELECT \* FROM users WHERE username=?;

Parameterized queries are one of the best methods to prevent SQL Injection. However, many existing applications still contain vulnerable legacy code. Therefore, detection systems remain necessary.

### ***1.3.3 Rule-based Web Application Firewall***

A Web Application Firewall (WAF) monitors HTTP requests before they reach the web server. Popular WAF solutions include:

* ModSecurity  
* OWASP Core Rule Set (CRS)  
* Cloudflare WAF

These systems compare incoming requests against thousands of predefined security rules. For example, a request containing UNION SELECT may immediately be blocked. Rule-based WAFs have several advantages such as: fast execution, easy to understand, low computational cost, high detection rate for known attacks. However, they also have several disadvantages, which are inability to detect new attack patterns, frequent requirement for manual update, high False Positive Rate, and easily bypassed using payload obfuscation.

Because of these limitations, many researchers have started using Artificial Intelligence to improve SQL Injection detection.

## **1.4 Machine Learning for SQL Injection Detection**

Machine Learning allows computers to learn patterns directly from data instead of relying only on manually written rules.

A typical machine learning workflow contains the following steps:

1\. Data collection

2\. Data preprocessing

3\. Feature extraction

4\. Model training

5\. Model evaluation

6\. Prediction

In SQL Injection detection, SQL queries are first converted into numerical feature vectors.

Common feature extraction techniques include: Bag of Words, TF-IDF, Character n-grams, Word n-grams. After feature extraction, classifiers such as Logistic Regression, Support Vector Machine (SVM), Random Forest, and XGBoost can be trained. Compared with rule-based detection, machine learning provides several advantages such as: better generalization, higher detection accuracy, better adaptability, and reduced manual rule creation. 

However, traditional machine learning still depends heavily on handcrafted features. Poor feature engineering often leads to poor model performance. This limitation motivates the use of deep learning models, which can automatically learn feature representations from raw SQL queries.

## **1.5 Deep Learning for SQL Injection Detection**

In recent years, deep learning has become one of the most popular approaches for cybersecurity tasks. Unlike traditional machine learning, deep learning models can automatically learn useful features from raw input data without requiring manual feature engineering.

For SQL Injection detection, deep learning models learn the semantic relationships between SQL keywords, operators, identifiers, and special symbols. As a result, they usually achieve better performance than traditional machine learning models when enough training data is available. The most common deep learning models used in SQL Injection detection include Convolutional Neural Networks (CNN), Recurrent Neural Networks (RNN), Long Short-Term Memory (LSTM), Gated Recurrent Unit (GRU), and Transformer-based models. Compared with traditional methods, deep learning provides several advantages like: automatic feature extraction, better ability to learn complex attack patterns, higher detection accuracy, and better generalization on unseen data. 

However, deep learning models also have several disadvantages that require more training data, more computational resources, longer training time, and more difficult to explain prediction results. Therefore, selecting an appropriate deep learning model is an important step in designing an AI-based SQL Injection detection system.

### ***1.5.1 Convolutional Neural Networks (CNN)***

Convolutional Neural Networks were originally developed for image processing. However, they have also shown good performance in text classification tasks. 

For SQL Injection detection, SQL queries are converted into token sequences before being processed by the CNN model. The convolution layers automatically identify important local patterns such as SQL keywords, operators, comments, and suspicious character combinations. Figure 1.1 illustrates the general CNN workflow.

![][image1]

***Figure 1.1.** General CNN workflow for SQLi detection (generic/illustrative).*

Compared with RNN models, CNN offers several advantages: faster training, lower computational cost, good feature extraction capability, and easy to deploy.  Because SQL queries are usually short, CNN can effectively learn local attack patterns while maintaining low inference latency. CNN is one of the four architectures empirically compared for Branch 1 in this project.

### ***1.5.2 Recurrent Neural Networks (RNN)***

Recurrent Neural Networks are designed to process sequential data. Unlike CNN, an RNN processes one token at a time while maintaining information from previous tokens. This characteristic allows RNNs to understand the order of SQL keywords. For example, the following two SQL statements contain similar words but have different meanings.

SELECT \* FROM users DROP TABLE users

The sequential information helps RNN distinguish between normal database operations and malicious SQL commands. 

However, standard RNN suffers from the vanishing gradient problem when processing long sequences. Therefore, LSTM and GRU were introduced to improve sequence learning.

### ***1.5.3 Long Short-Term Memory (LSTM)***

Long Short-Term Memory (LSTM) is an improved version of RNN. LSTM introduces memory cells and gating mechanisms that allow important information to be retained for a longer period. This makes LSTM suitable for processing long text sequences. For SQL Injection detection, LSTM can learn relationships between SQL keywords appearing far apart in the same query. Advantages of LSTM include: better long-term memory, higher detection accuracy, and better sequence modeling. Disadvantages include: slower training, higher memory usage, longer inference time.

Although LSTM performs well, many recent studies prefer Transformer-based models because they provide better parallel processing capability.

### ***1.5.4 Gated Recurrent Unit (GRU)***

GRU is another improvement over standard RNN. Compared with LSTM, GRU contains fewer gates and fewer parameters.  Therefore, GRU usually trains faster while maintaining similar performance. Compared with LSTM, GRU provides faster inference, smaller model size, lower memory consumption, and good sequence learning performance.

These characteristics make GRU a candidate worth revisiting for sequence-oriented detection work beyond this project’s current scope.

## **1.6 Transformer-based Models**

Transformer architecture has become the dominant approach in Natural Language Processing (NLP). Unlike RNN, Transformer processes all tokens simultaneously using the Self-Attention mechanism. Self-Attention allows the model to identify important relationships between different parts of a sentence regardless of their positions. Because SQL statements also have grammatical structures similar to natural language, Transformer models can effectively understand SQL syntax. Popular Transformer models include: BERT, RoBERTa, ALBERT, DistilBERT.

Among these models, DistilBERT is widely used because it provides a good balance between accuracy and computational cost.

### ***1.6.1 DistilBERT***

DistilBERT is a compressed version of BERT. It contains fewer parameters while preserving most of BERT's language understanding capability. Compared with the original BERT model, DistilBERT provides smaller model size, faster inference, lower memory usage, and similar prediction accuracy. Because this project focuses on real-time SQL Injection detection, DistilBERT is selected as one of the candidate models for the supervised learning branch.

This project's implementation empirically compares DistilBERT against three lighter alternatives (TF-IDF \+ Logistic Regression, TF-IDF \+ LightGBM, and a lightweight CNN with a SQL-specific tokenizer) and selects the final model for the supervised classification branch based on the F1-macro / latency / model-size trade-off.

### ***1.6.2 Why Not Use Large Language Models?***

Recently, Large Language Models (LLMs) such as GPT have achieved excellent performance in many NLP tasks. However, deploying LLMs inside a real-time database proxy presents several challenges. First, LLMs require large computational resources. Second, inference latency is much higher than lightweight Transformer models. Third, deployment cost is significantly higher. Finally, real-time SQL query filtering requires predictions within only a few milliseconds. Therefore, lightweight models such as DistilBERT or CNN are more suitable for this project.

## **1.7 Anomaly Detection**

Most supervised learning models require labeled attack data. However, new SQL Injection techniques appear continuously. Collecting labeled samples for every new attack is almost impossible. To solve this problem, anomaly detection is introduced as the second detection branch. Instead of learning malicious behavior, anomaly detection learns only normal database traffic. When a new SQL query is significantly different from normal behavior, it is considered suspicious. This approach provides the ability to detect unknown attacks.  Figure 1.2 illustrates the general anomaly detection workflow.

![][image2]

***Figure 1.2.** General anomaly detection workflow (generic/illustrative).*

Unlike supervised learning, anomaly detection produces a continuous anomaly score instead of a class label.

### ***1.7.1 Isolation Forest***

Isolation Forest is one of the most popular anomaly detection algorithms. The main idea is simple. Abnormal samples are easier to isolate than normal samples. The algorithm constructs many random decision trees, queries that require fewer splits to isolate are considered anomalies. Advantages include: fast training, low memory usage, suitable for high-dimensional data, good scalability.

Isolation Forest is one of the two algorithms empirically compared for Branch 2 in this project.

### ***1.7.2 One-Class SVM***

One-Class Support Vector Machine is another anomaly detection algorithm. Instead of separating two classes, One-Class SVM learns the boundary surrounding only normal data. Queries outside this boundary are classified as anomalies. Although One-Class SVM provides good detection accuracy, it usually requires careful parameter tuning and has higher computational complexity than Isolation Forest. Section 2.9 reports the empirical comparison between the two for this project's data.

### ***1.7.3 Role of Anomaly Detection in This Project***

In the proposed system, anomaly detection does not replace supervised classification. Instead, it complements the supervised classifier (Branch 1). For this midterm report, the anomaly score serves one purpose: identifying previously unseen SQL Injection attacks that Branch 1 was not trained to recognize.

This design allows the system to analyze not only the content of each SQL query but also its statistical abnormality, improving overall detection capability while maintaining acceptable computational cost.

## **1.8 Hybrid Detection**

A single detection method cannot identify every type of SQL Injection attack. Supervised learning performs well on known attacks but may fail when attackers use new payloads. On the other hand, anomaly detection can identify unusual behavior, but it usually produces a higher False Positive Rate because not every unusual query is malicious.

To overcome these limitations, this project combines two detection methods into one hybrid architecture.

•**Branch 1:** Supervised SQL Injection Classification

•**Branch 2:** Query-level Anomaly Detection

Each branch focuses on a different aspect of SQL Injection detection. The supervised model identifies known attack patterns. The anomaly detector identifies previously unseen behavior. Both predictions are combined by a decision rule. This two-branch architecture improves detection accuracy while reducing the weaknesses of either method alone.

### ***1.8.1 Two-Branch Detection Architecture***

The proposed system places an AI proxy between the web application and the database server. Every SQL statement passes through this proxy before reaching the database. The workflow can be summarized as follows:

1\. The web application generates a SQL query.

2\. The Database Proxy receives the SQL statement.

3\. The SQL statement is normalized through the canonicalization process.

4\. Branch 1 predicts whether the query belongs to a known SQL Injection category.

5\. Branch 2 calculates an anomaly score.

6\. The Decision Engine combines the outputs.

7\. The system decides to allow, block, or hold the request.

In this report, the supervised classification component (Branch 1\) and the query-level anomaly detection component (Branch 2\) have been implemented and evaluated on real data. The full multi-step Decision Engine sketched above has not yet been implemented as a running system; it is discussed as future work.

### ***1.8.2 Overkill Policy***

Instead of making only two decisions (Allow or Block), the proposed system introduces an additional security policy called **Overkill**. The purpose of Overkill is to reduce the risk of missing dangerous attacks. The decision rules are summarized below.

| Branch 1 | Branch 2 | System Action |
| ----- | ----- | ----- |
| Attack | – | Block immediately |
| Normal | Abnormal | Hold for administrator verification |
| Normal | Normal | Allow request |

The **Hold** action is an important feature because it allows administrators to verify suspicious queries before they are executed. Although this policy may slightly increase response time, it significantly improves system security. As with the rest of the Decision Engine, Overkill is a design described here and evaluated only conceptually; no administrator-review workflow has been built.

## **1.9 Related Work**

Many researchers have proposed Artificial Intelligence methods for SQL Injection detection \[1\]. Rather than re-explaining how each technique works — already covered in Sections 1.4–1.8 — this section summarizes what published studies actually applied, and what they consistently miss.

On the supervised side, classical machine learning pipelines (TF-IDF/n-gram features with SVM, Random Forest, and XGBoost) remain common because they are fast and cheap to deploy \[2\]; CNN-based classifiers are used where automatic feature extraction from raw query text is preferred \[3\]; and sequence models (LSTM/GRU) or their ensembles are applied when the goal extends to broader web-attack detection, not SQLi alone \[4\]. Transformer-based approaches — including SQLi-specific fine-tuned or hybrid BERT variants \[7, 8\], built on the general DistilBERT compression technique \[6\] — are increasingly reported, trading model size and inference latency for contextual accuracy.

On the unsupervised side, anomaly detection built on Isolation Forest \[9\] or One-Class SVM \[10\] is used specifically to catch attacks a supervised model was never trained on, at the cost of a higher false-positive rate than a well-tuned classifier alone.

A separate line of work studies how easily these detectors can be evaded rather than how well they classify: adversarial mutation tools such as WAF-A-MoLE \[11\] generate semantically-equivalent payload variants specifically to bypass ML-based WAFs — this is part of why Section 2.12.5 treats this report's F1/AUC figures as an upper bound, not a robustness guarantee.

Separately from technique choice, some intrusion-detection research also explores Continual Learning — updating a deployed model from new data without full retraining — as a way to keep pace with new attack variants; that direction is discussed further in Section 1.10.4 and is not implemented in this project (Conclusions, Future Work).

Across nearly all of the work above — supervised, anomaly-based, or hybrid — the prediction is made from a single query in isolation. Very few studies model the relationship between multiple queries generated in the same session, which is exactly the gap Section 1.10 develops.

**Table 1.1.** Comparison of Existing Detection Methods

| Method | Advantages | Limitations | Ref. |
| ----- | ----- | ----- | ----- |
| Rule-based WAF | Fast, simple, easy to deploy | Cannot detect new attacks | — |
| Machine Learning (SVM/RF/XGBoost) | Lightweight, good accuracy | Requires feature engineering | \[2\] |
| CNN | Automatic feature extraction | Needs labeled data | \[3\] |
| LSTM / GRU | Learns sequential information | Higher computational cost | \[4\] |
| Transformer / DistilBERT | High accuracy, understands context | Larger model size | \[6, 7, 8\] |
| Anomaly Detection | Detects unknown attacks | Higher False Positive Rate | \[9, 10\] |
| Hybrid Detection | Combines multiple strengths | More complex implementation | \[7\] |

From this comparison, it can be seen that no single method can solve every problem. Therefore, combining multiple detection approaches is a reasonable solution.

## **1.10 Research Gap**

After reviewing previous studies, several research gaps can be identified. These describe gaps in the *published literature*, not claims about what this project has already built — that distinction matters.

### ***1.10.1 Query-Level Detection Only***

Most AI-based SQL Injection detection systems treat every SQL query as an independent sample. The model predicts whether a single SQL statement is malicious without considering previous user activities. This assumption works well for traditional SQL Injection attacks but becomes ineffective against multi-step attacks.

### ***1.10.2 Difficulty Detecting Blind SQL Injection***

Blind SQL Injection usually consists of hundreds of SQL queries. Each individual query appears harmless. Only after observing the complete sequence does the attack pattern become obvious. Therefore, single-query classifiers cannot effectively detect this attack.

### ***1.10.3 Lack of Session-Level Analysis***

Most previous studies do not analyze SQL queries at the session level. They ignore information such as: query order, execution frequency, repeated access patterns, user behavior. These characteristics are important for detecting advanced SQL Injection attacks.

### ***1.10.4 Limited Adaptability***

Many published models remain static after deployment. When attackers create new SQL Injection techniques, detection performance gradually decreases. Few systems include a practical Continual Learning pipeline for updating models using administrator feedback.

### ***1.10.5 Contributions***

This report contributes two working, evaluated components: a supervised classifier for known SQL Injection categories (Branch 1\) and a query-level anomaly detector for previously unseen patterns (Branch 2). Both are built on a combined, carefully cleaned public dataset, with measured results.

These two components address query-level detection only: Branch 1 recognizes known attack syntax, and Branch 2 flags statistically abnormal queries that Branch 1 was not trained to recognize. The remaining gaps identified above — Blind SQLi's reliance on multi-query patterns (1.10.2), session-level analysis (1.10.3), and adaptability over time (1.10.4) — are not addressed by the current implementation and are left for future work.

# **CHAPTER 2\. EXPERIMENTAL RESULTS**

## **2.1 System Placement: The Database Proxy**

The proposed detection system is placed at the Database Proxy layer, between the web application backend and the database server. This placement — referred to internally as “Position B” — is a deliberate design choice: the proxy only observes a SQL statement **after** the backend has already assembled it from user input, and **before** it reaches the database engine.

This placement has two direct consequences for the threat model. First, it neutralizes horizontal query splitting (an attacker spreading a single payload across multiple request parameters), because the proxy only ever sees the final, concatenated SQL string — it does not need to reconstruct the query from separate parameters the way an input-layer WAF would. Second, it means the system cannot see anything upstream of query construction (raw HTTP parameters, headers) or downstream of query execution (result sets, out-of-band channels), which bounds the scope described in the Scope of the Study section and in Section 2.12.4 below.

*(Figure recommended here, not yet created: a diagram of this placement and the request flow through Branch 1 / Branch 2 — see List of Figures.)*

## **2.2 Canonicalization**

Before either branch processes a query, the raw SQL string passes through a canonicalization step that normalizes superficial syntactic variation (whitespace, letter case, comment style, equivalent literal encodings) so that the downstream models operate on a consistent representation. Canonicalization is shared across both branches and is the first line of defense against simple obfuscation; it does not, by itself, defend against the semantic-level evasion strategies discussed in Section 2.12.5.

**2.3 Data Sources**

Four public datasets were combined for this project, each contributing to Branch 1 (classification), Branch 2 (anomaly detection), or both. The table below summarizes them on a consistent basis; per-source row counts *after* filtering/re-labeling are given in Sections 2.4–2.5, since several sources were split, filtered, or merged before those final counts were produced.

| Dataset | Contents | Approx. size | Used in |
| :---- | :---- | :---- | :---- |
| **SQLiV3** | Raw SQL query strings, each labeled `normal` or a SQL Injection payload type. Kaggle-distributed. | \~30,000 rows | Branch 1 (attack \+ benign), Branch 2 (benign pool only) |
| **CSIC 2010** | Labeled HTTP requests (normal and anomalous) against a simulated e-commerce app; anomalous requests span multiple attack types (SQLi, XSS, buffer overflow, path traversal), not SQLi alone. | \~36,000 requests | Branch 2 only — benign pool (via session cookies) \+ held-out anomalous evaluation set |
| **payload-box** | Curated, attack-only list of standalone SQL Injection payload strings (no benign class). | A few thousand payloads | Branch 1 only — attack-side enrichment |
| **SR-BH 2020** | Honeypot-captured traffic with CAPEC-based multi-attack tags (SQLi, command injection, SSI, XSS, etc.), coarse (not sub-type-specific). | 527,813 rows total; 250,285 tagged SQL Injection | Branch 1 (attack sub-types, via re-tagging) and Branch 2 (benign pool, via content filtering) |

Because SR-BH 2020's tags are coarse and multi-attack, and because none of the four sources can be trusted as-is for a clean benign class, both branches apply their own content-based filtering/re-labeling on top of these raw sources rather than using the original labels directly — described separately for each branch below.

**2.4 Branch 1 — Supervised Multi-Class Classification: Methodology and Dataset**

Branch 1 classifies each canonicalized query into one of five classes: normal, union\_based, error\_based, boolean\_blind, time\_blind (a sixth class, `stacked`, was evaluated but excluded from final training — see below).

| Source | Role in Branch 1 | Processing applied |
| :---- | :---- | :---- |
| SQLiV3 | Base attack labels \+ benign queries | Re-labeled by attack sub-type |
| payload-box | Attack-side enrichment | Manually tagged, merged into the SQLiV3-derived pool |
| SR-BH 2020 | Additional attack sub-type variation \+ benign candidates | Rule-based sub-type re-tagging (attack side); content-based signature filtering (benign side) |

SR-BH 2020's re-tagging contributed the majority of usable per-class volume: \+83,189 union\_based, \+7,423 error\_based, \+126,926 boolean\_blind, \+32,747 time\_blind.

**Canonicalization.** Before feature extraction, every query (both branches) passes through a shared canonicalization step that normalizes case, whitespace, comment style, and equivalent literal encodings, so downstream models see a consistent syntax rather than superficial variation.

**Label-noise cleaning.**

* normal class: SR-BH 2020's own multi-label flags looked clean in aggregate, but manual review found real attacks mislabeled as benign (e.g. a sleep(15) time-based payload, a Shellshock payload). A content-based signature filter — independent of the source label — was applied over three iterative rounds, removing 2,892 rows (\~9.8% of the candidate normal pool).  
* boolean\_blind class (the catch-all for payloads not matching the other four explicit rules): a manual audit of 30 samples found \~13% mislabeled (SSRF, header injection, one benign row).

**Class handling and final dataset**

| Class | Status | Rows used |
| :---- | :---- | :---- |
| normal, union\_based, error\_based, boolean\_blind, time\_blind | Trained and evaluated (reported results) | 67,796 total → 54,236 train / 13,560 test |
| stacked | Included only in the 6-class architecture comparison to test learnability; 363 synthetic rows (no natural examples exist in any source) achieved 100% recall across all four candidates — a sign of trivial separability, not genuine signal | Excluded from the final reported training run |

In short: the **architecture comparison** (Table 2.2) uses all 6 classes to check whether stacked is learnable at all; the **final reported model** (Table 2.3 onward) uses the 5 real classes only, since stacked was excluded once it was shown to be an artifact of the synthetic template rather than a validated capability.

**2.5 Branch 2 — Query-Level Anomaly Detection: Methodology and Dataset**

Branch 2 is trained exclusively on benign traffic and produces a continuous anomaly score, rather than a class label — the goal is generalizing to attack syntax never seen during training.

**Dataset sources and roles**

| Source | Role in Branch 2 | Processing applied |
| :---- | :---- | :---- |
| SQLiV3 | Benign pool contributor | Content-filtered to remove any SQLi signature |
| CSIC 2010 | Benign pool contributor \+ anomalous evaluation set | Benign: session-cookie traffic pooled directly. Anomalous: 25,065 rows held out separately (multi-attack-type: SQLi, XSS, buffer overflow, path traversal — not SQLi-only) |
| SR-BH 2020 | Benign pool contributor | Content-filtered to remove any attack pattern (SQLi, and incidentally OS command injection, SSI, XSS) |

Unlike Branch 1's SQLi-only filter, Branch 2's benign pool must be clean of *any* abnormal traffic, so its content filter is broader than Branch 1's.

**Feature engineering.** Branch 2 deliberately avoids TF-IDF (vocabulary-dependent, so it wouldn't generalize to unseen attack syntax). Instead it computes four generic statistical/structural features per canonicalized query: length, ratio of special characters, count of SQL keywords, and Shannon entropy.

**Training and evaluation split**

| Set | Rows | Purpose |
| :---- | :---- | ----- |
| Benign train pool | 73,548 | Fit the anomaly model (One-Class SVM trained on a 12,000-row subsample — Section 2.12.6) |
| Benign held-out eval | 18,387 | Measure false-positive rate on clean traffic |
| Anomalous eval (CSIC 2010, held out) | 25,065 | Measure detection rate (multi-attack-type, so results should be read as general anomaly detection, not SQLi-specific — see Section 2.9) |

Total benign pool: 91,935 rows, after content filtering (\~7.4% of candidates rejected) and de-duplication (\~113,000 duplicate rows removed, mostly repeated static-asset requests from CSIC 2010/SR-BH 2020).

## **2.6 Decision Rule and the Overkill Policy**

The full project design combines the outputs of Branch 1, Branch 2, and (eventually) a session-level component through a central Decision Engine. **Only the Branch 1 \+ Branch 2 portion below has any empirical grounding in this report** — and even that is per-branch evaluation (Section 2.8–2.9), not an integrated, running decision service. Table 2.1 shows this two-branch decision rule.

**Table 2.1.** Decision Table (Two-Branch Design, Midterm Scope)

| Branch 1 | Branch 2 | System Action |
| ----- | ----- | ----- |
| Attack | — | Block immediately, log the request |
| Normal | Abnormal | HOLD for administrator verification (Overkill) |
| Normal | Normal | Allow |

The **Overkill** policy — holding a request rather than forcing an immediate allow/block decision — is intended to reduce the cost of a wrong decision at the expense of added latency and administrator workload. A fail-safe rule (deny-by-default on decision-engine timeout or failure) is part of the design but has not been implemented as a running system.

## **2.7 Evaluation Protocol**

Branch 1 is evaluated with per-class Precision/Recall/F1, F1-macro as the headline metric, a confusion matrix, and per-class ROC curves. Branch 2 is evaluated with false-positive rate and detection rate at a fixed operating threshold, AUC, a Precision-Recall curve (average precision), and a threshold sweep (21 threshold points, trading off FPR against detection rate and precision) to support a deployment-time threshold choice. Both branches report p50 inference latency and on-disk model size as deployment-relevant secondary metrics; the actual runtime environment (CPU/GPU used for latency measurement) should be stated alongside these numbers in the final camera-ready figures.

## **2.8 Branch 1 Results**

Table 2.2 reports the four-architecture comparison (6-class data, including stacked, at comparison time).

**Table 2.2.** Branch 1 Architecture Comparison

| Model | F1-macro | p50 latency | Model size | Train time |
| ----- | ----- | ----- | ----- | ----- |
| TF-IDF \+ Logistic Regression (chosen) | 0.985 | 0.5 ms | 3.9 MB | 10 s |
| TF-IDF \+ LightGBM | 0.993 | 60 ms | 6.0 MB | 264 s |
| DistilBERT | 0.992 | 2.8 ms (GPU) | 256 MB | 1,443 s |
| CNN \+ SQL-tokenizer | 0.987 | 0.3 ms | 116 KB (28K params) | 10 s |

TF-IDF \+ Logistic Regression was selected: the F1-macro spread across all four candidates is small (0.985–0.993), while LightGBM is roughly 120× slower per query (60 ms, too high for a real-time proxy) and DistilBERT requires a GPU and 256 MB on disk for no measurable F1 gain over the chosen model. The CNN is the strongest fallback candidate (smallest and fastest) if a future iteration needs stronger learned features than TF-IDF can provide.

After excluding the stacked class (Section 2.4) and retraining on the resulting 5-class, 67,796-row dataset, the model reaches **F1-macro \= 0.9822**. Table 2.3 gives the per-class breakdown.

**Table 2.3.** Branch 1 Per-Class Results (Test Set, n \= 13,560)

| Class | Precision | Recall | F1 | Support |
| ----- | :---: | :---: | :---: | :---: |
| normal | 0.966 | 0.947 | 0.956 | 3,000 |
| union\_based | 0.999 | 0.990 | 0.995 | 3,000 |
| error\_based | 0.998 | 1.000 | 0.999 | 1,560 |
| boolean\_blind | 0.948 | 0.974 | 0.961 | 3,000 |
| time\_blind | 1.000 | 1.000 | 1.000 | 3,000 |

![][image3]

***Figure 2.1.** Branch 1 — per-class ROC curves.*

The confusion matrix shows the only material confusion is between normal and boolean\_blind (157 normal rows misclassified as boolean\_blind; 74 boolean\_blind rows misclassified as normal), which is consistent with the \~13% measured label noise found in boolean\_blind during manual review (Section 2.4). As stated in the evaluation notes, this F1 score should not be read as “near-perfect” performance — it is measured on a clean test split, not on adversarially-perturbed input (Section 2.12.5).

## **2.9 Branch 2 Results**

Table 2.4 compares the two candidate algorithms.

**Table 2.4.** Branch 2 Algorithm Comparison

| Algorithm | Contamination | FPR | Detection Rate | AUC |
| ----- | :---: | :---: | :---: | :---: |
| Isolation Forest | 0.01 | 0.63% | 3.19% | 0.670 |
| One-Class SVM (chosen) | 0.005 | 0.30% | 20.73% | 0.902 |

One-Class SVM was selected for its substantially higher AUC and detection rate at a comparable (in fact lower) false-positive rate. On the held-out evaluation (3,000 benign, 25,065 anomalous, mixed-attack-type as noted in Section 2.5), the chosen model produces 9 false positives out of 3,000 benign queries (FPR \= 0.3%) and correctly flags 5,196 of 25,065 anomalous queries (detection rate \= 20.7%), with average precision (PR-AUC) \= 0.982.

![][image4]

***Figure 2.2.** Branch 2 — Precision–Recall curve (OCSVM).*

![][image5]

***Figure 2.3.** Branch 2 — anomaly score distribution, benign vs. anomalous.*

As noted in Section 2.5, the 20.7% detection rate is measured against a multi-attack-type evaluation set, not a SQLi-only one; it should be read as a general anomaly detection rate unless the evaluation set is first filtered to SQLi-only rows.

**Why a headline detection rate of 20.7% is consistent with AUC \= 0.902.** FPR and detection rate are both computed at a *single, fixed* decision threshold — the one corresponding to the deployed operating point (contamination \= 0.005). AUC, by contrast, integrates performance across the *entire* range of possible thresholds. A high AUC with a low detection rate at one specific point simply means the model separates benign from anomalous traffic well overall, and the deployed threshold was chosen deliberately conservative (to keep FPR — and therefore the Overkill/HOLD administrator workload, Section 2.6 — very low), not that the model is weak. A full sweep across 21 thresholds (report/metrics/branch2\_threshold\_sweep.csv) makes this trade-off explicit; Table 2.5 shows selected points from that sweep.

**Table 2.5.** Branch 2 Threshold Sweep (Selected Operating Points)

| Operating point | FPR | Detection Rate | Precision |
| ----- | :---: | :---: | :---: |
| Deployed (contamination \= 0.005) | 0.30% | 20.7% | 99.8% |
| Relaxed 1 | 3.17% | 33.2% | 98.9% |
| Relaxed 2 | 13.4% | 65.6% | 97.6% |
| Relaxed 3 | 20.5% | 87.1% | 97.3% |
| Relaxed 4 | 30.6% | 97.1% | 96.4% |
| Maximally relaxed | \~100% | 100% | — |

![][image6]

***Figure 2.4.** Branch 2 — FPR/Detection-Rate threshold trade-off.*

Detection rate rises sharply as the threshold is relaxed — reaching 97.1% at 30.6% FPR — which is exactly what a high AUC predicts. The deployed operating point was chosen at the very-low-FPR end of this curve because, under the Overkill policy (Section 2.6), every false positive becomes work for an administrator; the appropriate operating point is therefore a deployment/product decision, not a fixed property of the model, and Table 2.5 (or the full 21-point sweep) is the artifact that should be handed to whoever makes that decision.

## **2.10 Illustrative Demonstration**

A demonstration notebook loads the trained Branch 1 and Branch 2 models, accepts a SQL query as input, and returns a combined verdict. On a small, randomly-sampled set of 20 queries, 19 were classified correctly; the single error is consistent with the known normal ↔ boolean\_blind confusion described in. This notebook is an illustrative, minimal integration and should not be read as a demonstration of the full Decision Engine described in Section 2.6.

## **2.11 Summary of Results**

Branch 1 and Branch 2 both meet the accuracy targets set out in the Research Objectives, at latencies (0.5 ms and — for Branch 2, feature computation plus a linear SVM decision — comparably small) consistent with real-time proxy use. Branch 2's headline detection rate (20.7%) looks low in isolation, but Section 2.9 shows this is a deliberately conservative operating-point choice, not a weak model — AUC \= 0.902 and the threshold sweep (Table 2.5) confirm detection rate rises above 97% if a higher FPR is accepted.

## **2.12 Discussion and Limitations**

### ***2.12.1 Label Noise***

Two independent, measured sources of label noise were found during data construction rather than assumed: mislabeled normal rows in the SR-BH 2020 honeypot data requiring three rounds of content-based filtering (Section 2.4), and \~13% mislabeled samples in the boolean\_blind catch-all class from a small manual audit (30 samples). Both figures should be reported as measured limitations alongside the F1-macro \= 0.9822 result, since they plausibly explain the dominant confusion pattern in Table 2.3 and mean the “true” ceiling for this task, with clean labels, is unknown.

### ***2.12.2 Dataset Licensing***

payload-box (MIT) and SR-BH 2020 (CC0 1.0) have confirmed licenses. SQLiV3 does not: its original Kaggle listing carries no explicit license, and a GitHub mirror's self-applied MIT tag does not establish that the mirror actually holds redistribution rights over the underlying data. Until this is resolved, the combined dataset (which includes SQLiV3) should be treated as **provenance-unclear**, not as a cleanly MIT/CC0-licensed release, and this should be stated explicitly before any public dataset release (see also Conclusions, Future Work).

### ***2.12.3 Synthetic Data for the stacked Class***

No public source among SQLiV3, payload-box, or SR-BH 2020 contains naturally-occurring stacked-query examples. The 363 synthetic samples generated to represent this class are template-based and were found to be trivially separable (100% recall across all four candidate architectures) — a sign of low sample diversity, not of a solved sub-problem. This class was excluded from the reported training run for that reason (Section 2.4) and remains effectively unvalidated by this project.

### ***2.12.4 Threat Model Boundaries***

The system's placement at the Database Proxy (Section 2.1) defines clear boundaries. In scope: Union-based, Error-based, Boolean-blind, Time-blind, and Stacked-query SQL Injection. Explicitly out of scope: second-order SQL Injection (a payload stored safely in one request and triggered in a later, unrelated request, potentially days apart); out-of-band SQL Injection (data exfiltrated via DNS/HTTP channels the proxy never observes); and HTTP Parameter Pollution upstream of query construction, which the Position-B placement mitigates as a side effect rather than by design. Multi-step attacks that only reveal themselves across a sequence of queries (e.g., Blind SQLi carried out over many requests) are also outside what Branch 1 and Branch 2 can catch individually — closing that gap is exactly what the future-work session-level component (Conclusions) is intended for. These boundaries were already stated in the Scope of the Study section and are repeated here because they directly bound how the results in this chapter should be generalized.

### ***2.12.5 Adversarial Robustness Gap***

All results in this chapter are measured on clean, held-out test splits of the training distribution. No adversarially-perturbed test set (e.g., generated with a tool such as WAF-A-MoLE \[11\]) has yet been run against either branch. The F1-macro and AUC figures above should therefore be read as an upper bound on current performance, not as evidence of robustness to deliberate evasion — this is listed explicitly as unfinished work in the Conclusions.

### ***2.12.6 Methodological Open Points***

Two points are flagged here rather than silently accepted: (1) the Branch 2 One-Class SVM was trained on a 12,000-row subsample of the available 73,548-row benign pool (Section 2.5), and the effect of training on the full pool has not been measured; (2) manual label-noise auditing so far covers small samples (15–30 rows per class) rather than the \~100+/class cross-validated audit that would be needed to fully trust the noise-rate estimates in Section 2.12.1.

# **CONCLUSIONS**

## **Summary of Contributions**

This midterm report covers two working, evaluated components of a larger planned SQL Injection detection system: a supervised multi-class classifier (Branch 1, F1-macro \= 0.9822) and a query-level anomaly detector (Branch 2, One-Class SVM, AUC \= 0.902). Both were trained on a combined and carefully cleaned public dataset and evaluated with measured — not assumed — results, including a documented account of the label-noise issues found along the way (Section 2.12.1).

Everything beyond these two components — session-level detection across multiple queries, an integrated Decision Engine, the Overkill administrator-review workflow, and Continual Learning from administrator feedback — is part of the project's longer-term design (motivated by the research gaps in Section 1.10) but has **not** been implemented or evaluated. It is listed below as future work, not claimed as a current contribution.

## **Future Work**

The following items are known, scoped gaps rather than open-ended possibilities:

**1.Integrated system** (Database Proxy API, Decision Engine, administrator interface). Design exists (Section 2.6); no running integration beyond the illustrative demonstration notebook (Section 2.10).

**2.Session-level sequence detection**, end to end. No lab, no session data, no trained model — this is the largest remaining gap relative to the project's original motivation (Section 1.2.3, Section 1.10.3).

**3.Continual Learning loop**, connecting administrator feedback on held requests to periodic retraining with a validation gate.

**4.Concept drift monitoring in production** — periodic tracking of FPR/recall over time, model versioning and rollback.

**5.A production-grade Session Store** (TTL/eviction policy, and a shared backend such as Redis if the proxy runs as multiple instances) — a prerequisite for session-level detection.

**6.Latency/throughput benchmarking under realistic load** — current results measure correctness, not sustained throughput.

**7.Multi-round adversarial hardening** (iterated generate–test–retrain cycles against a tool such as WAF-A-MoLE) for Branch 1 and Branch 2\.

**8.Larger-scale, cross-validated manual label auditing** (\~100+ samples per class) to firm up the noise-rate estimates in Section 2.12.1.

**9.Resolving dataset licensing** before any public dataset release (Section 2.12.2).

**10.Broader comparison against published SOTA baselines**, appropriate for an extended (journal-length) version of this work.

# **REFERENCES**

**\[1\]**A. Paul, V. Sharma, and O. Olukoya, “SQL injection attack: Detection, prioritization & prevention,” Journal of Information Security and Applications, vol. 85, 2024, Art. no. 103871\. DOI: 10.1016/j.jisa.2024.103871.

**\[2\]**A. E. Widodo and F. F. D. Imaniawan, “Detection of SQL Injection, XSS, and Command Injection Attacks in Web Payloads Using SVM, Random Forest, and XGBoost,” Journal of Information Systems and Informatics, vol. 8, no. 3, 2026\. DOI: 10.63158/journalisi.v8i3.1655.

**\[3\]**A. Luo, W. Huang, and W. Fan, “A CNN-based Approach to the Detection of SQL Injection Attacks,” in Proc. 2019 IEEE/ACIS 18th Int. Conf. on Computer and Information Science (ICIS), 2019\. DOI: 10.1109/icis46139.2019.8940196.

**\[4\]**V. Babaey and H. R. Faragardi, “Detecting Zero-Day Web Attacks with an Ensemble of LSTM, GRU, and Stacked Autoencoders,” Computers, vol. 14, no. 6, Art. no. 205, 2025\. DOI: 10.3390/computers14060205.

**\[5\]**A. Vaswani, N. Shazeer, N. Parmar, J. Uszkoreit, L. Jones, A. N. Gomez, Ł. Kaiser, and I. Polosukhin, “Attention Is All You Need,” in Advances in Neural Information Processing Systems 30 (NeurIPS 2017), 2017\. arXiv:1706.03762.

**\[6\]**V. Sanh, L. Debut, J. Chaumond, and T. Wolf, “DistilBERT, a distilled version of BERT: smaller, faster, cheaper and lighter,” 2019\. arXiv:1910.01108.

**\[7\]**Y. Liu and Y. Dai, “Deep Learning in Cybersecurity: A Hybrid BERT–LSTM Network for SQL Injection Attack Detection,” IET Information Security, vol. 2024, Art. no. 5565950\. DOI: 10.1049/2024/5565950.

**\[8\]**D. Lu, J. Fei, and L. Liu, “A Semantic Learning-Based SQL Injection Attack Detection Technology,” Electronics, vol. 12, no. 6, Art. no. 1344, 2023\. DOI: 10.3390/electronics12061344.

**\[9\]**F. T. Liu, K. M. Ting, and Z.-H. Zhou, “Isolation Forest,” in Proc. 2008 8th IEEE Int. Conf. on Data Mining (ICDM), Pisa, Italy, 2008, pp. 413–422. DOI: 10.1109/ICDM.2008.17.

**\[10\]**B. Schölkopf, J. C. Platt, J. Shawe-Taylor, A. J. Smola, and R. C. Williamson, “Estimating the Support of a High-Dimensional Distribution,” Neural Computation, vol. 13, no. 7, pp. 1443–1471, 2001\.

**\[11\]**L. Demetrio, A. Valenza, G. Costa, and G. Lagorio, “WAF-A-MoLE: Evading Web Application Firewalls through Adversarial Machine Learning,” in Proc. 35th Annual ACM Symposium on Applied Computing (SAC '20), 2020\. arXiv:2001.01952.

*(These 11 references were located via web search to match the topics discussed in Chapter 1 and Section 2.12 — they are not necessarily the same sources the team's original literature-survey document used. Cross-check against the team's actual survey before finalizing, and replace any entry that doesn't match what was actually read.)*

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAl0AAAC9CAYAAACJWciAAAAa5klEQVR4Xu2dibsU1ZmH83/MTDJZJjNZzWgenUlMNJoJMRCjY2I0AwIiqIghoEHZZE0IXFCBqywiIBfUiIAi24WAAQRlJ2yKCggoqwqKimhCDV+1p6w61d33NF19vi583+d5nzr11dJ9v27u+dFd3fdzAQAAAADUnM/ZBQAAAADIHkIXAAAAgAcIXQAAAAAeIHQBAAAAeIDQBQAAAOABQhcAAACABwhdAAAAAB4gdAEAAAB4gNAFAAAA4AFCFwAAAIAHCF0AAAAAHiB0AQAAAHiA0AUAAADgAUIXAAAAgAcIXQAAAAAeIHQBAAAAeIDQBQAAAOABQhcAAACABwhdAAAAAB4gdAEAAAB4gNAFAAAA4AFCFwAAAIAHCF0AAAAAHiB0AQAAAHiA0AUAAADgAUIXAAAAgAcIXQAAAAAeIHQBAAAAeIDQBQAAAOABQhcAAACABwhdAAAAAB4gdAEAAAB4gNAFAAAA4AFCFwAAAIAHCF0AAAAAHiB0AQAAAHiA0AUAAADgAUIXAAAAgAcIXQAAAAAeIHQBAAAAeIDQBQAAAOABQhcAAACABwhdAAAAAB4gdAEAAAB4gNAFAAAA4AFCFwAAAIAHCF0AAAAAHiB0AQAAAHiA0AUAAADgAUIXAAAAgAcIXQAAAAAeIHQBAAAAeIDQBQAAAOABQhcAAACABwhdAAAAAB4gdAEAAAB4gNAFAAAA4IHMQ9d32jUE3247AjNy76G37RaX5aq7Hk6dA8/eRxastVtclrFPrEidA8/edgOn2y0uy449h1LnwLP3gg6j7BaX5aOP/546B1ZnpdjHY3VmTaah6/z2I8M7efDYqeDIOx9jld4x9pmKHvRbR8wM91/zyrHg1aMfY5VObd4W9nPPgbfsVhdl087Xw/2nLNkZbNr/MVbpok1Hw372n7jAbnVRTp8+He7fdXRz0LzjA6zS+VtPhP28qNN9dqtLIvv/sOv44NE172IGnt9+VEVzgAkKh49/lJpPsHLbDpxRUf9dyCx0jWhaGt45+05j9bo86O+fPBXuZwcHrF6X/guynx0csHqlrxKoWkL2s4MDVq/0ddqCdXa7U8h+U1a+mQoOWJ3S1wtvvNdudwp5VXj49OWp+QOrs8PQx53nABcyC11yp4ZMWZq6w1i9Lg94q+7jCV01Uvq6bddBu+UJlqzdSeiqkdLX9oNn2C1PQeiqjW2Hznb6HST72IEBq3fC0gPO/bfnDsxGl/67kmnoevXAidSdxeqV3r7z3km75Qlkn+6j56UCA1av9LbfhPJvcXUeVvjfkB0YsHqvG/BYi7/0du49TOiqkVOe3ddi/wVCV+107b89d2A2uvTflUxDl31HMRulty1dUC/7DJr611RgwOqV3nYbOctueYJf9ZlC6KqRt4xq+drGF7a9RuiqkbPXv9Vi/wVCV+107b89d2A2uvTfFUJXDiR06Uro0pXQpSuhS1/X/ttzB2ajS/9dIXTlQEKXroQuXQlduhK69HXtvz13YDa69N8VQlcOJHTpSujSldClK6FLX9f+23MHZqNL/10hdOVAQpeuhC5dCV26Err0de2/PXdgNrr03xVCVw4kdOlK6NKV0KUroUtf1/7bcwdmo0v/XSF05UBCl66ELl0JXboSuvR17b89d2A2uvTfFUJXDiR06Uro0pXQpSuhS1/X/ttzB2ajS/9dIXTlQEKXroQuXQlduhK69HXtvz13YDa69N8VQlcOJHTpSujSldClK6FLX9f+23MHZqNL/10hdOVAQpeuhC5dCV26Err0de2/PXdgNrr03xVCVw4kdOlK6NKV0KUroUtf1/7bcwdmo0v/XSF05UBCl66ELl0JXboSuvR17b89d2A2uvTfFUJXDiR06Uro0pXQpSuhS1/X/ttzB2ajS/9dIXTlQEKXroQuXQlduhK69HXtvz13YDa69N8VQlcOJHTpSujSldClK6FLX9f+23MHZqNL/10hdOVAQpeuhC5dCV26Err0de2/PXdgNrr03xVCVw4kdOlK6NKV0KUroUtf1/7bcwdmo0v/XSF05UBCl66ELl0JXboSuvR17b89d2A2uvTfFUJXDiR06Uro0pXQpSuhS1/X/ttzB2ajS/9dIXTlQEKXroQuXQlduhK69HXtvz13+PKfvtc2ob3duPnlg2W3l/Nsj8tCl/67QujKgYQuXQlduhK6dCV06evaf3vu8KEdtGTcfejDwZU3D4nqspz05LOJYLZg5dZwOWLS04lzyPK7V3WPxvHb0ApeLv13hdCVAwlduhK6dCV06Uro0te1//bc4UMJQue16ZZYF4uFLvuVLhnvPvBuNDZLO3TZY9+69N8VQlcOJHTpSujSldCl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>

[image2]: <data:image/png;base64,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>

[image3]: <data:image/png;base64,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>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAZ0AAAGCCAYAAAA7Xx7sAAAmj0lEQVR4Xu3dCZQU1dn/8QiouKBEoxDXiMclaowLhoivSwxo3miSN+objah4MhrBEBcSjSZRc1xiQv6KhGgCuEUxKERQQ4KiKOoR1DdEBVkVMCzGBWXfGZ7/ecpTNbeertvdM1bf6W6+n3PqTN3n3qquuj1Tv+npnu7PCAAAgXzGFgAAqBRCBwAQDKEDAAiG0AEABEPoAACCIXQAAMEQOgCAYAgdAEAwhE6devDBB5OlXFtvvbV07drVlotau3Zts2/HNX36dHnkkUdkzZo1tgtbsPh7auLEiVF79uzZLfo+e+qpp2TChAm2jFZE6NSYz3zmM9K2bVtbjmif66233iqo+XTo0EHmzp1ry2Vpzu3E7rvvvoJtbLvS9PYaGhqS9tlnnx3sGPR2Tj75ZFv2CnVcauedd07Ny8svvxzd/kknneSMqjy9ze985zsFtVI2bdqUOU5rxx13nC0jsMJ7BlVNf3B0+d3vfme7Cn7QWhIGLdGS29HQefjhh1O1+NxCsaET1/bcc89UbUtjQ0ddccUVQe8b1dLQ8Y3ZvHkzoVMFsu8dVC39gTr44IMzf7BszQ2DKVOmyDPPPJPqd2kAfPDBB7acMmPGDHn22WdtuVm3U0y1hI7vGPTPgHrhcr344osyadKkVM317rvvypNPPmnLXjp20aJFtuyl+9djKGXkyJG25JUVOsV+sdDbL3bMkydP9s7B6tWr5W9/+5stR1oSOocffnjRMTfeeKMtlW38+PHRz0BzzJ8/Xx5//HFb3qL57x1UpfgHaq+99ir44bLt+EKxcuXKpGbHaHvdunWptivex957753UfGP0Bz5mx5RDt7njjjtsuWL09uzFVWs77LBDqj1mzBhpbGxM2uq8885LnWO3bt3k6quvTtrnn39+ql/DwW3bi7iuu889bLXVVtHF2u13XXjhhala1iMRbd95552pdufOnZ0R2bJCJ+sXHW336NEj1bZzcNpppyXtfffdt+CcY6tWrcrcf3NDR/tLjYnpOH3EbWu2rUv8/d+mTZsoZLWm94Grd+/eqba7L/3+sPveUjELNcb+0B566KGZfcpe2JRt9+rVK9X++c9/LrfcckvSLmcf5YwpR0u2+TT09tyL6/33319wDNo+6qijknY8X1rXJ7dd9r5ZuHCh05vut3Om6+4vB/ob8ttvv53qd2l7wYIFBTXbvuqqq5L2r371q4IxWTR09Pmb+Il7DSrdTp8rcdl9jRs3ruCcLLem8+2y47VdLaET0znX+93+UqHsuWd9f9jalqi8ewdVI+sbfc6cOZl99sKmbFtpcMU/XLq4P+jl7KOcMaU0d3we9Db333//KEj0ImIvgvEY+6ej559/PvN43VpWv8vOmb5yUNudOnVyRjWx+7PtuHbXXXel2h999FHS/sc//pG5nWUf6eg22223nTOi9Bzoq86y+l366E8fOei4eHFpu9pCx6X1ZcuWRev69dvf/naqz9La7rvvbstbnMKZQVWz38zxn3n0N2PbZy9sqlR74MCBwUOn3LG33nprFBDNWYrR27V/RrKyjm348OGZdVep/qw5U3rx0rou7nNjdqxtxzV9pOq2Xc8991yqFt+OLu4T7DZ0lI4544wzknapOSjVf8ABBxT0Z7WrOXS++MUvJn12jG2jCTNTY7K+meMfDNuXdWFz24MGDSrov/3224OGjh3X3P/D+DT0tu3F1bLHF8uqu8deqt/OmT1vfU7H7bf7s+245v6/kx1jQ8cnK3T0EaHd1rZVuXOgfbY/q93c0Fm+fLl3zOLFi6N/DYjpOP0ZiGVtm3WcrrjPfc7Trbv0pef8z5AQOrUm65tZZf1w2Aubctv6j522v3379sFCp2PHjrZU1nZ50duyF1fLdzxat/9I647V9SOOOMLpTffbObO3s88++xTt1/Zhhx1WUCvW/jSho+y22rav5rPH7PYPGzYsejGB2n777TP3Z9vNDR2lT9rfdttttlywrbb322+/pO0LVltzaZ/7wpNY//79i35/bMmYhRpxww03JD8Avm9etx7/ALnj3fYll1wS1T7++OOktu2220Z/XvNtY9vxPsoZY+krfdxxdh+VVs5tuv16IbPGjh2b9GcF6GOPPZb0f+UrX0nqWbetL6t1a9dff33mePc5H3f/Xbp0SerK3Ubvgy9/+csFt5nFHWPH6QtMbF3PK6796Ec/ckZ/4uijj0769YUGrr59+yZ98Z+JdYn/cdhdBg8enGqXsn79+uTRoi49e/a0QyL6j9baHz9Scfef9TOUxffP2qW+P7ZU/pkEACBnhA4AIBhCBwAQDKEDAAiG0AEABEPoAACCIXQAAMHUZei4r61nYWFhYan8Uq7yR9aQ5kwAAKDl3nzzzWZdc8sfmaP4HXVL0Tc8jFN05syZtturnH0DAD69qg+dnXbaKfqo5VIHad8XrNR4V3PGAgBarupDR5UTOtrvfgzv73//e3n00UedEX6l9g0AyEddhY5rxYoVqY9DLsZuG/vj63+MFgC1Rd+tWj9JdcaMGSytsOjTG/aTY2N1GzpK3wU5i461S5bD7j8sWkJZtm6ZvPb+a/Lk/Cfl4ZkPy6Apg+RXk34lVzx7hZw79lz5xl+/IceNOC45rtZcjnzgSOn3TD+56KmLovb4d8bLhH9PkL/N/ZuMmj1Khs8YLkPfGCoDXh0gK9c3fawyEIK9CLK0zhJ/UqqrbkPnnXfekVNPPTVV87HbxuILbHMsXbtU+j7dt+AizeJf1m5ca6cRaDF9hPP+++/bMgJbsmRJFDxWXYXOvffem7R//OMfy4IFC5wRfr59xxfFYho3N8r/PPY/BRfSUsuJD58oDU82yE2Tb5KHZjwkz/77WZn10SxZv2m9vYmatmTNEvnne/+MztPOQTlL1we7ypmPnynPL3ze7hrIpBe6jRs32jIC0/ug7kLnyCOPTNYXLlyYGpM13sc3Nr7wZdG/GdsLZLzc8NINMvOj8l+yvSWzcxd6icNfH532HNUz+vPmmo1NH+GM2kPoVIeaDZ34OZd4sX2W1vSje5sjaz8qvjBZ7kVLn2tBGBrm+hyShkQ8/9e8cE30XJeu82fN8pcL/nGBfPfx78rJj5ws33z0mzJi5ghZtWGVnfKaROiIDB06VH7961/bcqYrr7xSRo8ebcsR3cc111xjy9LY2CjXXXedDB8+3HYlajZ0QvBNQPwDmlWzddQ+/dOmPkIdPWd09AKIn7/4c7lv2n3Rff2/T/yvHP3g0dH6SY+cFH096oGj5JjhxyTfD/814r+iPwf+96P/Lef+/dyCC32tLs8teM5OVVWr9tDJ+gVa/eY3v4nqw4YNS9a7du1qh5Wk22koxOs+kydPTvr/85//FIx12+66vkBLP5pbLV++vGC7GKFThG8C4h+62I2TbiyoAbVCH8k8Nf8p+c0rv5G7XrtLHpz+oHx95Nfl9NGnFwSNb9GQ/b///J/MWzbP7r5qVHvofP3rX8+85syfP7+gbtvlOOWUU5L1tm3byrXXXuv0NtF9r1u3Lmlvs802yfrUqVOlT58+Sbtjx45y2GGfXPfsq4K7dOkibdq0SdUUoVOEbwLcgNnYuJHAwRZp9YbVBeFTzcuoF0fJtPemyZsfvllymbFkhry/+v3oFZR6nsvXLY9e/KK1xSsXy7+X/1vmLpsbjdPx7yx/R+YunRu96Gf6kukF+7OLPnLWgNZl4YqFMv6f46OaXnM6de4k7616T95d+W60v2mzp0V1PY4V61dEx6Jt/VcK/beDpeuWRn36y8Oq9auir5saN0XXpljnzp2de05kwoQJ3uubrV966aXSu3fvpL3HHnsk6zpWn1vP0q1bN2nXrp0tEzrF+CYg/ia268CWTC9yC1YsiB4hXTXxKrl58s0FF359RHTqX0+V3uN6S6+/9yroj5duD3WT74z5jvzgyR/ITyf+NKrpdnZccxYbOra/EosNG9+i1xr9+vDTDyfr8fLUlKdStYlvTky1dd232P3Hy+S5n/wJza25Y19666WkvW37bWX/g/aXD9d8GL2Ypnv37lGInXzyyfKDH/zAfhskfNdPQqcI3wTE31B2HUD1sn9eswFRiUX/dUKXdZvWRcuGTRuiR0z6qGbRikXRI535y+ZLx892jC7wuq7XHf2qiz6aikMnXrbeZutoex1fzqOqOEjctoaKrcXLvWPuTfo0BPftsq90P6l75r50Xf/vxtIXIZxzzjm2HCF0ivBNQPwNFT+ZrP+FD6C62dCpFrvvvnsqVHRx/4E96zkdl93WXWKnn3569OR+bMiQIUX36Ro5cqS8++670bpu4wbUhKmf/Jkubuu/jEycODEZn4XQKcI3Afa3mX+9/y87BECVqdbQybrOuLVSoVOuo446KlnX/d1+++1Ob5P+/fun2u5td+jQIZlDfeR2x/13pEJnyMghcuChBybthoaGZNsYoVOEbwJs6ACoftUYOq+88orMm1f4ij+99qxc+cl7E+YVOrqP9957L1mP6aMSt92pUyc54YQTonV9AcGxxx6b9Cl3rK6/+uqr0fofHvpD1D6j1xnJou3pH37yJ0B9FKQInSJ8E0DoALWnGkOnnrl/hosXRegU4ZsAQgeoPYRO64lDR1/9RugU4ZsAN3D0v88BVD9Cp/UsWrkoCR5CpwjfBLih86fX/2S7AVQhQqd1xaGzYcMGQsfHNwFu6Ojr5AFUP0Kndem7JmjorN+wntDx8U0Az+cAtUcvdOvX19fnUtWSOHT0fd0IHQ/fBBA6QO3ZtGlTdLHT/6DXRzwsYZeVa1bK1EVTZfr06YSOj28CCB2gNs2cOTO64LG0zqLvf6dLFkJHCB0AyFOx6yahI4QOAOSp2HWT0BFCBwDyVOy6SegIoQMAeSp23SR0hNABgDwVu24SOkLoAECeil03CR0hdAAgT8Wum4SOEDoAkKdi101CR0qHztce+ZrtAgB4EDol+CYgnriznjjLdgEAPAidEnwTEE9cv2f62S4AgAehU4JOwBNPPJEssQv+3wXRcv2w62XWrFlRzR0Xj9U+W7Nji22fVbP1rFqx7Z977rmCmh27YsWKglqx7XV8qe11uzy2d2u+7WPlbp9Vs/WsWrHtP+1939rbZ9VsPatWbPus+96Ozbrvi21v7/us7fneK9y+2H1fye3ja2fW9n/4wx8IHd8ExGl9+z9vt10AAI8bXrohWrLwSEdKh85DMx6yXQCAFiB0pHTojJs3znYBAFqA0JHSofPCwhdsFwCgBQgdKR060z6cZrsAAC1A6Ejp0Jm3bJ7tAgC0AKEjpUPnwzUf2i4AQAsQOlI6dDY0brBdAIAWIHSkdOgAAPJB6AihAwChEDpC6ABAKISOEDoAEAqhI4QOAIRC6AihAwChEDpC6ABAKISOEDoAEAqhI4QOAIRC6AihAwChEDpC6ABAKISOEDoAEAqhI4QOAIRC6AihAwChEDpC6ABAKFUfOiNGjIgOUJeXXnrJdqfst99+ydivfvWrttvLNwGEDgDkq+pDxz24Ygd67rnnlj3W8o0ldAAgX1UdOj/72c/k5ZdfTtp//OMfvQer9YaGhqR91FFHOb3F+fZJ6ABAvqo6dLbaaqtUe9WqVd6DXbJkCY90AKDKVXXoZB1YVi02YMCAqF+XYcOG2e5EPMZdshA6AJCvqg6dz3/+86n23LlzvQer9alTpybt+++/X2666SZnhJ9vn4QOAOSrqkNn/PjxMmTIkKTdp08fadOmjTOiiT2JxsbGgtDysdvGCB0AyFdVh45yD07XNUxibqhoX79+/ZL2cccdF4VWOXwTQOgAQL6qPnTUYYcdJrvssostS9u2bVPtKVOmRI+EOnXqJPPmzUv1FeObAEIHAPJVE6FTab4JIHQAIF+EjhA6ABAKoSOEDgCEQugIoQMAoRA6QugAQCiEjhA6ABAKoSOEDgCEQugIoQMAoRA6QugAQCiEjhA6ABAKoSOEDgCEQugIoQMAoRA6QugAQCiEjhA6ABAKoSOEDgCEQugIoQMAoRA6QugAQCiEjhA6ABAKoSOEDgCEQugIoQMAoRA6QugAQCiEjhA6ABAKoSOEDgCEQugIoQMAoRA6QugAQCiEjhA6ABAKoSOEDgCEQugIoQMAoRA6QugAQCiEjhA6ABAKoSOEDgCEQugIoQMAoRA6QugAQCiEjhA6ABAKoSOEDgCEQugIoQMAoRA6QugAQCiEjhA6ABAKoSOEDgCEQugIoQMAoRA6QugAQCiEjhA6ABAKoSOEDgCEQugIoQMAoRA6QugAQCiEjhA6ABAKoSOEDgCEQugIoQMAoRA6QugAQCiEjhA6ABAKoSOEDgCEUvWhM3DgwOgAdXn88cdtd8rmzZujcW3atGneSXnGEjoAkK+qDx334HS9sbHR6U1zx2oAlcs3AYQOAOSrqkOnf//+MmXKlKR9zz33eA9W6/PmzbPlsvj2SegAQL6qOnTsga1Zs6agFtP6smXLoq+6bLvttnaIl2+fhA4A5KumQsdXU3HYxA466CBZsmSJM6JJPNZdshA6AJCvVguds88+25YK7L333qn2W2+95T1YrT/wwAMFtXL4xhE6AJCviofOyJEjCx5V6FJO6Dz//PNy5513Ju2GhgZp166dM6KJ7vOGG25I1XbddddU28c3AYQOAOSr4qGjOx8+fLi88cYbMm3atGQpJ3SUe3D2QN0Amj17dqp/n332kY0bNybtYux+Y4QOAOSroqGjj1Ty0KNHDznkkENsWTp37mxL0XM5Xbt2teWifBNA6ABAvioaOqpXr162FCn3kU4IvgkgdAAgXxUPHfd5HHchdABgy1Px0PGFi6/eGnwTQOgAQL4qHjoTJ060pcjChQttqdX4JoDQAYB8VTx0YjNnzpSpU6faclXwTQChAwD5qnjo6D942udz2rZta4e1Kt8EEDoAkK+Kh07WP2iedNJJsnLlSltuNb4JIHQAIF8VDZ1x48bZUqJv37621Gp8E0DoAEC+Kho66nvf+54tyf333x+9K0G18E0AoQMA+ap46MTP45xxxhly1llnJe1q4jseQgcA8lXx0FH6Hmlx2HTv3t12tzrfBBA6AJCvIKGT5d5777WlVuObAEIHAPJV8dDRd3rOWnhHAgDY8lQkdHSHF198cbKetRA6ALDlqUjouHzh4qu3Bt8EEDoAkK+Kh04t8E0AoQMA+ap46IwYMUImTZoUrb/++uvRjd18881mVOvyTQChAwD5qnjoHH300cl6fEM33XSTzJkzJ6m3Nt8EEDoAkK+Khs7YsWOT9euvv17atGmTtC+66KJkvbX5JoDQAYB8VTR0Zs+eLevWrYvW9UYWLVqU9P3yl79M1lubbwIIHQDIV0VDR+nOddF3JVA9e/Zs1g2G4DseQgcA8lXx0KkFvgkgdAAgX60WOvyfDgBseSoSOjvttJM8+OCD0Xr85zW7EDoAsOWpSOj861//StZ94eKrtwbfBBA6AJCvioSOa+LEibYU8dVbg28CCB0AyFfFQ8e6/fbbbanV+SaA0AGAfFU8dHTngwYNStqXX355s24wBN/xEDoAkK+Khs7ixYtl2rRptiybNm2S0aNH23Kr8U0AoQMA+apo6Lzwwgu2lPjpT39qS63GNwGEDgDkq6Kho7J23r59e1tqVVnHqAgdAMhXxUOnX79+0Q24y5FHHmmHtSrfBBA6AJCviodOLfBNAKEDAPkidITQAYBQKh46H3/8cfJnNaVf+/TpY0a1Lt8EEDoAkK+Kh078kQb6sdWxGTNmRJ+1Uy18E0DoAEC+Kho6Tz/9dLLuho5qaGhItVuTbwIIHQDIV0VDZ9asWfLBBx9E627oNDY2pt6loLX5JoDQAYB8VTR0VPx8Tvfu3aVXr16p53eqhe94CB0AyFfFQ0fp8zpu+FQb3wQQOgCQr4qHzmuvvWZLVcc3AYQOAOSroqEzduxY2WGHHWy56vgmgNABgHxVNHTWr18vXbt2teUIH+IGAFueioaO+sIXvmBLET6uGgC2PBUPnfgFBHYhdABgy1Px0PGFi6/eGnwTQOgAQL4qHjq1wDcBhA4A5KtioeP+KW3evHm2u6r4JoDQAYB8VSR0LrvssujdB9ScOXOadQOtwXd8hA4A5KsioWN3ePzxx6fa1cYeb4zQAYB8BQkd+w7TihcSAMCWp+pD5yc/+Um0v7Zt28qdd95puzPp+DFjxtiylz3eGKEDAPmqWOiUWsoNHffgdH3Dhg1Ob6E2bdoQOgBQpSoWOqWUEzr9+vWTadOmJe0HHnig5L7jj8cmdACg+lQkdPJiD2zt2rUFNVfcR+gAQHWqqdDx1dSjjz4qDz30ULReKnS03y5ZCB0AyFdVh06XLl1Sbf3466yD3bx5s+y1115Ju1ToWFn7VIQOAOSrqkPn1VdflYEDBybtCy64QNq3b++M+MTgwYPloIMOShY9oT333DNaL4dvAggdAMhXVYeOcg/OHqhtx3ikAwDVqepDR1144YVyyimn2HLmB8S5j3jOPfdc253JNwGEDgDkqyZCp9J8E0DoAEC+CB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACKXqQ6dXr17RAe62225y3XXX2e7EwQcfHI3r2rVr9PWxxx6zQ7x8E0DoAEC+qj503IPT9TVr1ji9TexJ2HYxvrGEDgDkq6pD55JLLpGZM2cm7REjRpR9sOWOU76xhA4A5KuqQ8ce2Pr16wtqPuWOU76xhA4A5KumQsdXs6655ho54YQTbDmh+7BLFkIHAPJV1aFz4IEHptrTp08vebA9e/aUu+++25aL8u2T0AGAfFV16EydOlUGDBiQtM855xzZcccdnRFpq1evlgceeMCWS/JNAKEDAPmq6tBR7sHZA3XbK1askHbt2jm95bP7jRE6AJCvqg8dpc/RXHDBBbYsp59+erJ+4oknFizl8k0AoQMA+aqJ0Kk03wQQOgCQL0JHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEIhdITQAYBQCB0hdAAgFEJHCB0ACIXQEUIHAEKp+tDp0aOHtG3bVg499FC5+OKLbXeKjj3mmGOiEyo11uWbAEIHAPJV9aHjHpyuL1u2zOlt8vrrrxeMLZdvLKEDAPmq6tBpaGiQt99+O2mPGjXKe7Bat2MHDx7sjPDz7ZPQAYB8VXXo2APbsGFDQS1m6zr2wAMPTNV87LYxQgcA8lVToeOrqax6+/btbSmiY+2ShdABgHxVdegccsghsnnz5qQ9bdo078Fq3Y7t1auXM8LPt08AQL6qOnTmzJkjN998c9I+88wzpWPHjs6IJnoSdqz+ia0czZkAAEDLVXXoKPfg7IG6bX2UU2xsMc0ZCwBouaoPHXXHHXfI1Vdfbcty0UUX2ZJceeWVMnToUFsuqjkTAABouZoInUprzgQAAFqO0JFPQoeFhYWFJdxSrvJH1oHmJnI907nQBXxfWMxFE+aiSV5zkc9eagQXlyaEThO+L9KYiybMRZO85iKfvdQILi5NCJ0mfF+kMRdNmIsmec1FPnupEVxcmhA6Tfi+SGMumjAXTfKai3z2AgBAGQgdAEAwhA4AIBhCBwAQTF2Gzq677ho96bXnnnvargI6rtyxtei0006Lzq9Nmza2K0XfeDWeiwEDBtjuurDHHnsk51iO2267reyxteb8888vey70rajisdtuu63trnkTJkxIzm/Tpk22OyUeV8681So9t0suucSWC1x22WUtmovmja4BdgJs22X7vvWtb6XatU7Pb9KkSal2OTp06OB99+9adeqpp6ba5cyFblPOuFqjv4D85S9/SdrFzvHCCy9MtYuNrUV6cd1rr72SdrHzs322XQ/iN1ouFTo77LBD6pfT5sxF+SNrhD152441NjYW9Nl2rbPnY9s+t956a9lja4U9H227n9dknXLKKdFXu109sOek7VtuuSVVi9mx9UbPb9WqVUlbf/FctmyZM6KJnQvbrhd6XqVCx567bRdT/sgaYU9e26NGjUrV1G9/+9vMsfXEnk+7du1SbZ8DDjgg+sC9emLnQtsDBw5M1Vzbbbdd9NVuVw/sOXXp0kXatm2bqsV07LHHHht9tdvVA3tOTzzxhFx++eWpWkzHjhw5Mlr/4IMPCratF3pezQ2dE044QRYuXJiq+dTdrNnJ0Lb7YXCxhoaGzLH1YunSpQXns/fee8u6detStSx2u3pgz0nbffr0SdVi7li7XT2w53T88ccX1GK2btu1zp7PlClT5Bvf+EaqFhszZkw0/s9//nP09dprr7VD6oKeW3ND5/vf/74888wzqZpPfX0HSeFkaHvcuHGpmrrrrrsyx9YTez62nWXHHXe0pbpgz13bw4YNS9XUl770pdQn1Nrt6oE9p86dO3vvdztW2y+//HKqVsvs+T388MPyi1/8IlWL2bHanjVrVqpWD/S8mhs6Xbt2jX7RLUfd/UTZybBtl+2z7Vpnz8e2rc9+9rMyf/58W64L9txtO6b1rOXFF1+0Q2uWPXdt62/vWbLGTps2LVWrZXo+7p+Funfv7n0FW9ZcnHHGGalaPdDzam7o2HYx5Y+sETvttFPypKh+Eqn7ypStt9461daxMR27fPnypF0P9OH/5z73uWj9nXfeSX1jXHzxxXLjjTcmbftNY9u17uOPP5a+ffsmbffVeTvvvHO0ZKm3eVBDhgxJXvqs8+Keo/7suG19ubT7Hn31Nh8bN25MnZO7vnr16tTzoNqnNbddj7JCJ/6TYmzs2LGy1VZbRetr165t1lyUP7KGXHrppdEk2I/EPvLII+W8885L1fS3+6yx9eKRRx6Jzu9rX/taQf3555+P1uMfPLvUm6uuuio6r1122SVV79GjR7S4Jk+eXNdz8fTTT0fndcwxx6TqL7zwgmyzzTapWvzS8e233z5Vrxf66jU9P30ZsHX44Yen2vvuu2801v2FtZ74rgHTp08v+F8//TOrjjn00ENT9VLq76cJAFC1CB0AQDCEDgAgGEIHABAMoQMACIbQAQAEQ+gAAIIhdBCE/i+Qu4Rk/+fAtou54ooroq/usfv+Y31LYO/HUPfl448/bkuoUeX95AE5cC/0+p5V2v7Tn/7kjKgc/ac+VzmhY8do++yzz44+EsH3z5Wl6Db6ZrN5sccY19q3b2/LuYnnQa1Zs0YOOuigzOMoprnj33777cx/3kTtad49D3wKWRearFolNDd0+vfvb0upi61bK7UvV4jQqTTfPCxevDhVK6Ylx92pUycZPHiwLaPGNP+eB1oo60Jja4sWLUou5Lroh+259K044j5djz+I7ZVXXkltd88996S2a27oZPVnXWzj+g9/+MOkbc8hpu9e7Nb1o8Rj+j5Wcd1+XPj777+f2i7+FFS3Fu8v63btWH2vLFt310td2HWMnQet6Vv/x/TtdNzb1HdvdseWc5xZfHXUDu5BBGMvGHrxdN+AtdSnuZ544ony97//PWnrmzHOnDkzWrdv2Knbuc+9VDp04vGlzkHX7SMd/Tyb0aNHJ20dM378+Gg9/vhgl92fpW/WWGxMVnvQoEGpdjF2HuL3LnM1t51Vs21fDbWFexDB6AVDP6Ey/q3evdDF/fai4rZtn34Mg+/zTOyFsTmh8+STT2b223269Xh8OedgQ8eO/+53v1t0f+6nfNo+5YZO1idcals/Q8dtu2zb0n69D/U4dH2PPfawQwrYfdr27NmzC2ravvvuuwtqqG3cgwjGXjC07f75TNu66MXMXeJHLHZ71xFHHBH1z5s3L2rr+nHHHZf0Nyd0/vrXv2b2a63c0Cl2DlmhY8fHwaJ9xV6skHWcbujoR3bYMfoiA7dm+23bsvOgj0D3339/Z4QkLy6IPxDP7tO2zzrrrMx50HeBd9ntUHu4BxGMvWA89thjBRc/93NuLLu9y/Zpu6Whs2TJksx+e7F162+88UayXuocskLHR/v0c6B8srZ1Qyf+iGWXtt1aVn8xWfNgt2lu+7777iuoZSlnDKob9yCCybpguDX9YCg7xn3Ox/b17t1bhg4dmtmn7ZaGjsrq911sS52D29b1+DOd4rodv379+uQDssrZn10v5zmd+BFh3HbZtqX9WfPQp0+fVNtVrP3Nb36zoKb0c4/sK+LsGNQe7kEEoReLeHF16NAhVf/oo49SY/X/M1z64oG4z/17/1tvvZXaLl70eR+3feuttxa0s9gPMrP7jZcs9hxc+uemuB5/iJ7SRzNxPX51Wqw5+3PH6Z+9Ym593bp1mfWstuX2x38CVEuXLk1tp5826o6NFx2nunXrlnk77tgFCxak+q677jrZbbfdUjXUnuzvLAAFnzCK1mUDCrWJexHw0EdZZ555pi2jFRA49YN7EgAQDKEDAAiG0AEABEPoAACCIXQAAMEQOgCAYAgdAEAwhA4AIBhCBwAQDKEDAAjm/wNjxWPGxUxedgAAAABJRU5ErkJggg==>

[image5]: <data:image/png;base64,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>

[image6]: <data:image/png;base64,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>