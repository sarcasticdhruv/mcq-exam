from flask import Flask, render_template, request, redirect, url_for, session
import os
import pdfplumber
import re
import uuid
import json
from werkzeug.utils import secure_filename
import google.generativeai as genai

app = Flask(__name__)
app.secret_key = 'mcq_exam_prep_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database simulation (in-memory for this example)
exams_db = {}
results_db = {}

# Set up Gemini API (you'll need to replace with your actual API key)
GEMINI_API_KEY = "AIzaSyC9PkLrGeeumDDqfEH65mq9k96HXPKrrbM"
genai.configure(api_key=GEMINI_API_KEY)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def enhance_mcq_extraction(text, raw_mcqs):
    """Use Gemini to verify and complete MCQs with answers and justifications"""
    model = genai.GenerativeModel('gemini-2.5-pro-preview-05-06')
    
    prompt = f"""
You are given a block of text containing multiple-choice questions. I have already extracted the questions and options, but the correct answers and justifications are missing or incomplete.

Please do the following:
- Match each question with its correct answer (only one correct choice per question).
- Provide a brief justification for each answer.
- Do not rewrite the questions or options.
- Return your response **only** as a JSON array with the following fields per question:
  - question_number (string)
  - question_text (string)
  - options (object with keys "a", "b", "c", "d")
  - correct_answer (one of "a", "b", "c", or "d")
  - justification (string)

Respond ONLY with valid JSON. No explanation, no markdown, no prose.

Here is the raw PDF text:
{text}

Here are the parsed MCQs:
{json.dumps(raw_mcqs, indent=2)}
"""

    try:
        response = model.generate_content(prompt)
        response_text = response.text
        print("GEMINI RAW RESPONSE:\n", response_text[:1000])  # Debug: print first 1000 characters

        # Strip markdown code block markers or garbage
        cleaned = re.sub(r'^```(json)?|```$', '', response_text.strip(), flags=re.MULTILINE).strip()

        try:
            improved_mcqs = json.loads(cleaned)
        except json.JSONDecodeError:
            print("JSON parsing failed, using raw_mcqs fallback.")
            return raw_mcqs

        # Ensure all questions include a valid answer and normalize it
        for q in improved_mcqs:
            if 'correct_answer' not in q or q['correct_answer'].lower() not in ('a', 'b', 'c', 'd'):
                print(f"Warning: Question {q.get('question_number')} missing valid correct_answer.")
                q['correct_answer'] = None
            else:
                q['correct_answer'] = q['correct_answer'].strip().lower()

        return improved_mcqs

    except Exception as e:
        print(f"Error processing Gemini response: {e}")
        return raw_mcqs  # Fallback

def extract_mcqs_from_pdf(file_path):
    mcqs = []
    try:
        with pdfplumber.open(file_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
        
        # Try to parse rough MCQ blocks using regex
        raw_mcqs = []
        questions = re.split(r'\n(?=\d{1,3}\.\s)', full_text)
        for q_block in questions:
            match = re.match(r'(\d{1,3})\.\s+(.*?)(?=\na\)|\na\.|\na\s)', q_block, re.DOTALL)
            if not match:
                continue
            question_number = match.group(1).strip()
            question_text = match.group(2).strip()

            options = {}
            option_matches = re.findall(r'([a-dA-D])[\).]?\s+(.*?)(?=\n[a-dA-D][\).]?\s+|$)', q_block, re.DOTALL)
            for opt in option_matches:
                options[opt[0].lower()] = opt[1].strip()

            raw_mcqs.append({
                'question_number': question_number,
                'question_text': question_text,
                'options': options,
                'correct_answer': None,
                'justification': ""
            })

        if GEMINI_API_KEY and raw_mcqs:
            return enhance_mcq_extraction(full_text, raw_mcqs)
        else:
            return raw_mcqs

    except Exception as e:
        print(f"Error extracting MCQs: {e}")
        return []

@app.route('/')
def index():
    return render_template('index.html', api_configured=(GEMINI_API_KEY != ""))

@app.route('/configure_api', methods=['POST'])
def configure_api():
    global GEMINI_API_KEY
    api_key = request.form.get('api_key', '')
    if api_key:
        GEMINI_API_KEY = api_key
        genai.configure(api_key=GEMINI_API_KEY)
        return redirect(url_for('index'))
    return "API Key is required", 400

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'pdf_file' not in request.files:
        return redirect(request.url)
    
    file = request.files['pdf_file']
    
    if file.filename == '':
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        # Generate unique ID for this exam
        exam_id = str(uuid.uuid4())
        
        # Save the file
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{exam_id}_{filename}")
        file.save(file_path)
        
        # Process the PDF
        mcqs = extract_mcqs_from_pdf(file_path)
        
        if not mcqs:
            return "No MCQs found in the uploaded PDF. Please check the format.", 400
        
        # Store the MCQs in our "database"
        exams_db[exam_id] = {
            'title': request.form.get('exam_title', 'Untitled Exam'),
            'questions': mcqs,
            'file_path': file_path
        }
        
        return redirect(url_for('exam_preview', exam_id=exam_id))
    
    return "Invalid file type. Please upload a PDF.", 400

@app.route('/exam/<exam_id>/preview')
def exam_preview(exam_id):
    if exam_id not in exams_db:
        return "Exam not found", 404
    
    exam = exams_db[exam_id]
    return render_template('exam_preview.html', exam=exam, exam_id=exam_id)

@app.route('/exam/<exam_id>/start')
def start_exam(exam_id):
    if exam_id not in exams_db:
        return "Exam not found", 404
    
    exam = exams_db[exam_id]
    
    # Initialize session data for this exam
    session['current_exam'] = {
        'exam_id': exam_id,
        'answers': {},
        'start_time': None  # You could add timing functionality
    }
    
    return render_template('take_exam.html', exam=exam, exam_id=exam_id)

@app.route('/exam/<exam_id>/submit', methods=['POST'])
def submit_exam(exam_id):
    if exam_id not in exams_db or 'current_exam' not in session:
        return "Exam not found or session expired", 404
    
    # Get submitted answers
    answers = {}
    for key, value in request.form.items():
        if key.startswith('q_'):
            question_num = key.split('_')[1]
            answers[question_num] = value
    
    # Calculate results
    exam = exams_db[exam_id]
    correct_count = 0
    results = []
    
    for question in exam['questions']:
        q_num = question['question_number']
        user_answer = answers.get(q_num, '')
        is_correct = user_answer == question['correct_answer']
        
        if is_correct:
            correct_count += 1
        
        results.append({
            'question_number': q_num,
            'question_text': question['question_text'],
            'user_answer': user_answer,
            'correct_answer': question['correct_answer'],
            'is_correct': is_correct,
            'justification': question['justification']
        })
    
    # Store results
    result_id = str(uuid.uuid4())
    results_db[result_id] = {
        'exam_id': exam_id,
        'score': correct_count,
        'total': len(exam['questions']),
        'percentage': round(correct_count / len(exam['questions']) * 100, 2),
        'details': results
    }
    
    # Clear session
    session.pop('current_exam', None)
    
    return redirect(url_for('show_results', result_id=result_id))

@app.route('/results/<result_id>')
def show_results(result_id):
    if result_id not in results_db:
        return "Results not found", 404
    
    result = results_db[result_id]
    exam = exams_db[result['exam_id']]
    
    return render_template('results.html', 
                          result=result, 
                          exam=exam, 
                          result_id=result_id)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
