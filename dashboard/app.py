from flask import Flask, render_template

# Import all blueprints

from projects.employee_performance.app import performance_bp
from projects.student_records.app import records_bp
from projects.student_tests.app import tests_bp

app = Flask(__name__)

# Register blueprints

app.register_blueprint(performance_bp, url_prefix='/employee-performance')
app.register_blueprint(records_bp, url_prefix='/student-records')
app.register_blueprint(tests_bp, url_prefix='/student-tests')

# Dashboard projects
projects = [
    {"name": "Intern Allocation", 
     "url": "http://localhost:8501"},
    {"name": "Employee Performance Tracker", "url": "/employee-performance"},
    {"name": "Student Records & Attendance", "url": "/student-records"},
    {"name": "Student Tests", "url": "/student-tests"},
    {
        "name": "Training & Management System",
        "url": "http://127.0.0.1:8000/"   # 👈 Django URL
    },
    {
        "name": "Management System",
        "url": "https://displaylive.netlify.app/"   # 👈 Django URL
    },
     {
        "name": "Liveboard",
        "url": "http://127.0.0.1:5001"   # 👈 your liveboard URL
    },
]
  
@app.route('/')
def index():
    return render_template("index.html", projects=projects)

if __name__ == "__main__":
    app.run(debug=True, port=5000)


