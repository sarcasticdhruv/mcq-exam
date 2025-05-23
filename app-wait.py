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
GEMINI_API_KEY = ""
genai.configure(api_key=GEMINI_API_KEY)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def enhance_mcq_extraction(text, raw_mcqs):
    """Use Gemini to improve MCQ parsing or provide better justifications"""
    model = genai.GenerativeModel('gemini-2.5-pro-preview-05-06')
    
    prompt = f"""
    I need help extracting and organizing multiple-choice questions from this text:
    
    {text}
    
    I've already extracted some information but need verification:
    {json.dumps(raw_mcqs, indent=2)}
    
    Please correct any errors and ensure all questions, options, correct answers and justifications are properly extracted.
    Return the result as valid JSON.
    """
    
    try:
        response = model.generate_content(prompt)
        # Parse the response and extract the formatted MCQs
        response_text = response.text
        
        # Find JSON content if surrounded by markdown code blocks or other text
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```|```\s*([\s\S]*?)\s*```|({[\s\S]*})', response_text)
        if json_match:
            json_content = next(group for group in json_match.groups() if group is not None)
            improved_mcqs = json.loads(json_content)
            return improved_mcqs
        else:
            # Try to parse the entire response as JSON
            improved_mcqs = json.loads(response_text)
            return improved_mcqs
    except Exception as e:
        print(f"Error processing Gemini response: {e}")
        return raw_mcqs  # Fall back to original extraction

# def extract_mcqs_from_pdf(file_path):
    """Extract MCQs from PDF using pattern recognition"""
    mcqs = []
    
    try:
        with pdfplumber.open(file_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            
            # Look for questions matching pattern: number followed by period/question mark and text
            question_pattern = r'(\d+)\.\s+(.*?)\s+(?:a\.|b\.|c\.|d\.)'
            option_pattern = r'([a-d])\.\s+(.*?)(?=\s+[a-d]\.|(?:Correct\s+)?Answer:|$)'
            answer_pattern = r'(?:Correct\s+Answer|Answer):\s*(?:\()?([a-d])(?:\))?'
            justification_pattern = r'Justification:\s+(.*?)(?=\d+\.|$)'
            
            # Find questions
            questions = re.finditer(question_pattern, full_text, re.DOTALL)
            
            for q_match in questions:
                q_num = q_match.group(1)
                q_text = q_match.group(2).strip()
                
                # Extract full question text until the next question
                q_end_pos = q_match.end()
                next_q_match = re.search(r'\d+\.', full_text[q_end_pos:])
                if next_q_match:
                    q_full_text = full_text[q_match.start():q_end_pos + next_q_match.start()]
                else:
                    q_full_text = full_text[q_match.start():]
                
                # Extract options
                options = {}
                for opt_match in re.finditer(option_pattern, q_full_text, re.DOTALL):
                    opt_letter = opt_match.group(1)
                    opt_text = opt_match.group(2).strip()
                    options[opt_letter] = opt_text
                
                # Extract answer
                answer_match = re.search(answer_pattern, q_full_text)
                correct_answer = answer_match.group(1) if answer_match else None
                
                # Extract justification
                justification_match = re.search(justification_pattern, q_full_text, re.DOTALL)
                justification = justification_match.group(1).strip() if justification_match else ""
                
                mcqs.append({
                    'question_number': q_num,
                    'question_text': q_text,
                    'options': options,
                    'correct_answer': correct_answer,
                    'justification': justification
                })
        
        # Use Gemini API to enhance the extraction if we have an API key and found some questions
        if GEMINI_API_KEY != "YOUR_API_KEY" and mcqs:
            enhanced_mcqs = enhance_mcq_extraction(full_text, mcqs)
            if enhanced_mcqs:
                return enhanced_mcqs
                
        return mcqs
    except Exception as e:
        print(f"Error extracting MCQs: {e}")
        return []

def extract_mcqs_from_pdf(file_path):
    mcqs = []
    try:
        with pdfplumber.open(file_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"

            # Split the text based on 'ANSWER:' to isolate each MCQ
            question_blocks = re.split(r'ANSWER:', full_text)
            for i in range(len(question_blocks) - 1):
                block = question_blocks[i]
                answer = question_blocks[i + 1].strip().split()[0].upper()

                # Extract question number and text
                q_lines = block.strip().split("\n")
                question_text = ""
                options = {}
                for line in q_lines:
                    if re.match(r'^\s*[A-Da-d][\).]?\s+', line):
                        option_match = re.match(r'^\s*([A-Da-d])[\).]?\s+(.*)', line.strip())
                        if option_match:
                            options[option_match.group(1).upper()] = option_match.group(2).strip()
                    else:
                        question_text += " " + line.strip()
                question_text = question_text.strip()
                q_number = len(mcqs) + 1
                mcqs.append({
                    'question_number': str(q_number),
                    'question_text': question_text,
                    'options': options,
                    'correct_answer': answer,
                    'justification': ""
                })
        return mcqs
    except Exception as e:
        print(f"Error extracting MCQs: {e}")
        return []

@app.route('/')
def index():
    return render_template('index.html', api_configured=(GEMINI_API_KEY != "AIzaSyC9PkLrGeeumDDqfEH65mq9k96HXPKrrbM"))

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
