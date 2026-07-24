# **AI-BASED SQL INJECTION DETECTION SYSTEM**

## **INTRODUCTION**

### **Background**

With the rapid growth of web applications, protecting databases has become one of the most important tasks in cybersecurity. Modern websites store a large amount of sensitive information such as personal data, passwords, banking information, and business records. Because of this, databases are common targets for attackers.

SQL Injection (SQLi) is one of the oldest and most dangerous web vulnerabilities. It allows attackers to insert malicious SQL commands into user input fields. If the application does not validate user input correctly, these commands can be executed directly by the database management system. As a result, attackers may read confidential information, modify records, delete data, or even gain administrator privileges.

Although many organizations use Web Application Firewalls (WAFs) to protect their systems, traditional rule-based security solutions still have several limitations. They mainly rely on predefined signatures and manually written rules. New attack techniques, obfuscated payloads, and zero-day attacks can bypass these defenses. At the same time, strict rules may incorrectly classify normal queries as malicious, increasing the False Positive Rate (FPR).

Recently, Artificial Intelligence (AI) and Machine Learning (ML) have become promising technologies for cybersecurity. Instead of depending only on predefined rules, AI models can learn attack patterns from historical data and recognize previously unseen attacks. Deep learning models such as CNNs and Transformer-based models have shown high accuracy in many SQL Injection detection studies.

However, most existing AI-based SQL Injection detection systems only analyze individual SQL queries. They ignore the relationship between multiple queries generated within the same user session. Some advanced attacks, especially Blind SQL Injection and Query Splitting attacks, cannot be detected by analyzing only a single query. Their malicious behavior only becomes visible after observing a sequence of related queries.

Therefore, this project proposes an AI-Based SQL Injection Detection System that combines multiple AI techniques into a unified architecture. The system performs detection at both query level and session level, providing better security while maintaining acceptable response time.

## **Research Objectives**

The main objective of this project is to develop an intelligent SQL Injection detection system using Artificial Intelligence techniques.

The proposed system has the following objectives:

* Detect common SQL Injection attacks with high accuracy.  
* Detect unknown or zero-day attacks through anomaly detection.  
* Analyze user sessions to identify multi-step SQL Injection attacks.  
* Reduce False Positive Rate while maintaining fast response time.  
* Support continual learning so that the system can improve over time using administrator feedback.  
* Build a complete prototype including AI models, backend APIs, and a Streamlit demonstration interface.

## **Scope of the Study**

The proposed system focuses on SQL Injection detection at the Database Proxy layer. The proxy receives SQL statements after the backend application has generated the final SQL query but before the query reaches the database server.

The project mainly studies three detection branches:

* Supervised SQL Injection Classification  
* Query-level Anomaly Detection  
* Session-level Sequence Detection

The following topics are outside the scope of this project:

* Cross-Site Scripting (XSS)  
* Cross-Site Request Forgery (CSRF)  
* Second-order SQL Injection  
* Out-of-band SQL Injection  
* Network intrusion detection  
* Malware analysis

## **Research Methodology**

This project follows an experimental research methodology.

First, datasets containing normal SQL queries and SQL Injection payloads are collected and preprocessed.

Second, different AI models are trained and evaluated, including supervised learning models, anomaly detection models, and sequence learning models.

Third, all detection modules are integrated into a Database Proxy architecture.

Finally, the complete system is evaluated using different performance metrics, including Accuracy, Precision, Recall, F1-score, False Positive Rate, and Inference Latency.

# **CHAPTER 1: THEORY**

## **1.1 Overview of SQL Injection**

SQL Injection is one of the most common web security vulnerabilities. It occurs when user input is directly included in SQL statements without proper validation or parameterization.

Normally, a web application receives input from users through forms, search boxes, or URLs. The backend application combines these inputs into SQL statements before sending them to the database. If the application does not sanitize user input correctly, attackers can insert malicious SQL commands.

For example, a normal login query may be written as:

| SELECT \* FROM users WHERE username='admin' AND password='123456'; |
| :---- |

An attacker may enter the following password:

| ' OR '1'='1 |
| :---- |

The SQL statement becomes:

| SELECT \* FROM users WHERE username='admin' AND password='' OR '1'='1'; |
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

| SELECT \* FROM users WHERE id=1 AND SUBSTRING(database(),1,1)='m'; |
| :---- |

If the condition is true, the web page behaves normally.

If the condition is false, the page changes slightly.

By repeating this process many times, attackers can recover database information character by character.

Each SQL statement may appear harmless when viewed independently. However, the attack pattern becomes obvious when many related queries are analyzed together.

This limitation motivates the Session-Level Detection Branch proposed in this project.

### **1.2.4 Time-based Blind SQL Injection**

Time-based Blind SQL Injection is similar to Boolean-based attacks, but the attacker observes response time instead of page content.

A common payload is

| SELECT \* FROM users WHERE id=1 AND IF(1=1,SLEEP(5),0); |
| :---- |

If the database delays its response for five seconds, the attacker knows that the injected condition is true.

Time-based attacks are difficult to detect because every SQL statement looks almost normal.

Only the response time and repeated request pattern reveal the attack.

### **1.2.5 Stacked Queries**

Some database management systems allow multiple SQL statements in one request.

For example,

| SELECT \* FROM users; DROP TABLE users; |
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

| SELECT \* FROM users WHERE username='" \+ username \+ "'"; |
| :---- |

Safe query:

| SELECT \* FROM users WHERE username=?; |
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

**![][image1]**

Compared with RNN models, CNN offers several advantages.

* Faster training.  
* Lower computational cost.  
* Good feature extraction capability.  
* Easy to deploy.

Because SQL queries are usually short, CNN can effectively learn local attack patterns while maintaining low inference latency.

### **1.5.2 Recurrent Neural Networks (RNN)**

Recurrent Neural Networks are designed to process sequential data.

Unlike CNN, an RNN processes one token at a time while maintaining information from previous tokens.

This characteristic allows RNNs to understand the order of SQL keywords.

For example, the following two SQL statements contain similar words but have different meanings.

| SELECT \* FROM users DROP TABLE users |
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

In this project, GRU is considered a suitable candidate for the Session-Level Detection Branch because it can efficiently analyze sequences of SQL queries generated within the same user session.

Compared with LSTM, GRU provides

* Faster inference.  
* Smaller model size.  
* Lower memory consumption.  
* Good sequence learning performance.

These characteristics make GRU suitable for real-time applications.

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

This project's implementation empirically compares DistilBERT against three lighter alternatives (TF-IDF + Logistic Regression, TF-IDF + LightGBM, and a lightweight CNN with a SQL-specific tokenizer) and selects the final model for the supervised classification branch based on the F1-macro / latency / model-size trade-off (see Chapter 4).

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

The general workflow is shown below.

![][image2]

Unlike supervised learning, anomaly detection produces a continuous anomaly score instead of a class label.

This score is later combined with the supervised classifier in the decision module.

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

Therefore, Isolation Forest is selected as one candidate algorithm for the anomaly detection branch.

### **1.7.2 One-Class SVM**

One-Class Support Vector Machine is another anomaly detection algorithm.

Instead of separating two classes, One-Class SVM learns the boundary surrounding only normal data.

Queries outside this boundary are classified as anomalies.

Although One-Class SVM provides good detection accuracy, it usually requires careful parameter tuning and has higher computational complexity than Isolation Forest.

For this reason, Isolation Forest is generally more suitable for large-scale real-time systems.

### **1.7.3 Role of Anomaly Detection in This Project**

In the proposed system, anomaly detection does not replace supervised classification.

Instead, it complements the first detection branch.

The anomaly score has two important purposes.

First, it identifies previously unseen SQL Injection attacks that may not exist in the training dataset.

Second, the anomaly score is combined with the learned query embedding before being sent to the Session-Level Detection Branch.

This design allows the system to analyze not only the content of each SQL query but also its statistical abnormality.

As a result, the overall detection capability can be improved while maintaining acceptable computational cost.

## **1.8 Hybrid Detection and Continual Learning**

A single detection method cannot identify every type of SQL Injection attack. Supervised learning performs well on known attacks but may fail when attackers use new payloads. On the other hand, anomaly detection can identify unusual behavior, but it usually produces a higher False Positive Rate because not every unusual query is malicious.

To overcome these limitations, this project combines multiple detection methods into one hybrid architecture. The proposed system consists of three independent detection branches that work together.

* **Branch 1:** Supervised SQL Injection Classification  
* **Branch 2:** Query-level Anomaly Detection  
* **Branch 3:** Session-level Detection

Each branch focuses on a different aspect of SQL Injection detection.

The supervised model identifies known attack patterns.

The anomaly detector identifies previously unseen behavior.

The session model analyzes the relationship between multiple SQL queries generated during the same user session.

Finally, all predictions are combined by a central decision module.

This multi-branch architecture improves detection accuracy while reducing the weaknesses of individual models.

### **1.8.1 Three-Branch Detection Architecture**

The proposed system places an AI proxy between the web application and the database server. Every SQL statement passes through this proxy before reaching the database.

The workflow can be summarized as follows.

1. The web application generates a SQL query.  
2. The Database Proxy receives the SQL statement.  
3. The SQL statement is normalized through the canonicalization process.  
4. Branch 1 predicts whether the query belongs to a known SQL Injection category.  
5. Branch 2 calculates an anomaly score.  
6. Branch 3 analyzes recent queries from the same session.  
7. The Decision Engine combines the outputs.  
8. The system decides to allow, block, or hold the request.

In this project, the supervised classification component (Branch 1) and the query-level anomaly detection component (Branch 2) have been implemented and evaluated on real data (see Chapter 4). Branch 3 and the complete three-branch Decision Engine described above are a designed contribution of this project — the main intended contribution — but have not yet been implemented or evaluated; they are discussed as future work (Chapter 6).

### **1.8.2 Overkill Policy**

Instead of making only two decisions (Allow or Block), the proposed system introduces an additional security policy called **Overkill**.

The purpose of Overkill is to reduce the risk of missing dangerous attacks.

The decision rules are summarized below.

| Branch 1 | Branch 2 | Branch 3 | System Action |
| :---- | :---- | :---- | :---- |
| Attack | \- | \- | Block immediately |
| Normal | Abnormal | \- | Hold for administrator verification |
| Normal | Normal | Suspicious session | Hold entire session |
| Normal | Normal | Normal | Allow request |

The **Hold** action is an important feature because it allows administrators to verify suspicious queries before they are executed.

Although this policy may slightly increase response time, it significantly improves system security.

### **1.8.3 Continual Learning**

Cybersecurity is constantly changing.

New SQL Injection techniques appear every year.

A static machine learning model gradually becomes outdated if it is never updated.

To solve this problem, the proposed system applies a simple Continual Learning mechanism.

The workflow is shown below.

![][image3]

When administrators review held requests, their decisions become new labeled training samples.

These samples are added to the training dataset.

The AI model is retrained periodically.

Before deployment, the updated model must pass validation tests.

Only models that improve performance are deployed.

This process allows the detection system to gradually adapt to new attack patterns.

## **1.9 Related Work**

Many researchers have proposed Artificial Intelligence methods for SQL Injection detection. Existing studies mainly focus on improving classification accuracy using machine learning and deep learning techniques.

Traditional machine learning approaches commonly use TF-IDF, Bag-of-Words, or n-gram features together with classifiers such as Support Vector Machine (SVM), Random Forest (RF), Naïve Bayes (NB), and XGBoost.

These methods usually provide fast inference and low computational cost. However, their performance depends heavily on manually designed features.

More recent studies have applied deep learning models.

CNN-based methods automatically extract local features from SQL queries and usually achieve better detection accuracy than traditional classifiers.

LSTM and GRU models further improve detection by learning sequential information inside SQL statements.

Recently, Transformer-based models such as BERT and DistilBERT have become popular because they understand contextual relationships between SQL tokens more effectively.

Several studies have reported very high classification accuracy using Transformer models. However, these models require more computational resources and have higher inference latency than lightweight CNN models.

Another research direction focuses on anomaly detection.

Instead of learning attack signatures, anomaly detection models learn normal database behavior.

Algorithms such as Isolation Forest, One-Class SVM, Local Outlier Factor (LOF), and Autoencoders have shown good performance in detecting unknown attacks.

However, anomaly detection alone often produces more false alarms because unusual behavior is not always malicious.

Hybrid detection systems combine supervised learning with anomaly detection.

Research has shown that hybrid systems are more robust against unseen attacks while maintaining good performance on known attacks.

Some recent studies also investigate Continual Learning, allowing intrusion detection systems to update themselves using new training data without completely retraining from scratch.

Although these approaches improve adaptability, most published systems still analyze SQL queries independently.

Very few studies consider the relationship between multiple SQL queries generated during the same user session.

### **Table 1.1 Comparison of Existing Detection Methods**

| Method | Advantages | Limitations |
| :---- | :---- | :---- |
| Rule-based WAF | Fast, simple, easy to deploy | Cannot detect new attacks |
| Machine Learning | Lightweight, good accuracy | Requires feature engineering |
| CNN | Automatic feature extraction | Needs labeled data |
| LSTM / GRU | Learns sequential information | Higher computational cost |
| DistilBERT | High accuracy, understands context | Larger model size |
| Anomaly Detection | Detects unknown attacks | Higher False Positive Rate |
| Hybrid Detection | Combines multiple strengths | More complex implementation |

From this comparison, it can be seen that no single method can solve every problem.

Therefore, combining multiple detection approaches is a reasonable solution.

## **1.10 Research Gap**

After reviewing previous studies, several research gaps can be identified.

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

### **1.10.5 Contribution of This Project**

Based on the identified research gaps, this project proposes several improvements.

**First**, the system combines supervised learning, anomaly detection, and session-level detection into a unified three-branch architecture.

**Second**, instead of analyzing only individual SQL queries, the proposed system analyzes complete user sessions, allowing it to detect Blind SQL Injection and multi-step attacks more effectively.

**Third**, an Overkill policy is introduced. Instead of immediately allowing or blocking every request, suspicious requests can be temporarily held for administrator verification. This mechanism reduces the risk of false decisions.

**Finally**, the system supports Continual Learning. Administrator feedback is converted into new labeled data, enabling periodic model retraining and improving long-term detection capability.

These contributions distinguish the proposed system from many existing SQL Injection detection approaches and provide a more practical solution for real-world deployment.

[image1]: <data:image/png;base64,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>

[image2]: <data:image/png;base64,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>

[image3]: <data:image/png;base64,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>