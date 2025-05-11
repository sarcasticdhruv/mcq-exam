from flask import Flask, render_template, request, redirect, url_for, session
import os
import re
import uuid

app = Flask(__name__)
app.secret_key = 'mcq_exam_prep_key'
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database simulation (in-memory for this example)
exams_db = {}
results_db = {}

def extract_mcqs_from_text_file(file_path):
    mcqs = []
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            text = file.read()

        # Split questions by finding patterns like "1. Question text"
        questions = re.split(r'\n\d+\.\s', text)
        questions = [q.strip() for q in questions if q.strip()]  # Remove empty questions

        for q in questions:
            lines = q.split('\n')
            if len(lines) < 3:
                continue  # Skip if not enough lines for question and options

            question_text = lines[0].strip()
            options = {}
            correct_answer = None

            for line in lines[1:]:
                if re.match(r'[A-D]\.\s', line):
                    options[line[0]] = line[3:].strip()
                elif line.startswith('ANSWER:'):
                    correct_answer = line.split(':')[1].strip()

            if question_text and options and correct_answer:
                # Extract question number
                match = re.search(r'^\s*(\d+)\.', question_text)  # Modified regex here
                question_number = match.group(1) if match else None
                
                # Clean the question text
                question_text = re.sub(r'^\d+\.\s*', '', question_text).strip()

                mcqs.append({
                    'question_number': question_number,
                    'question_text': question_text,
                    'options': options,
                    'correct_answer': correct_answer,
                    'justification': ''  # No justification in the file
                })

    except Exception as e:
        print(f"Error extracting MCQs: {e}")
        return []

    return mcqs

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'text_file' not in request.files:
        return redirect(request.url)

    file = request.files['text_file']

    if file.filename == '':
        return redirect(request.url)

    if file:
        # Generate unique ID for this exam
        exam_id = str(uuid.uuid4())

        # Save the file
        filename = "all.txt"  # Fixed filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{exam_id}_{filename}")
        file.save(file_path)

        # Process the text file
        mcqs = extract_mcqs_from_text_file(file_path)

        if not mcqs:
            return "No MCQs found in the uploaded text file. Please check the format.", 400

        # Store the MCQs in our "database"
        exams_db[exam_id] = {
            'title': request.form.get('exam_title', 'Untitled Exam'),
            'questions': mcqs,
            'file_path': file_path
        }

        return redirect(url_for('exam_preview', exam_id=exam_id))

    return "Invalid file type.", 400

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
        user_answer = answers.get(question['question_number'], '').upper()  # Ensure comparison is case-insensitive
        is_correct = user_answer == question['correct_answer'].upper()

        if is_correct:
            correct_count += 1

        results.append({
            'question_number': question['question_number'],
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