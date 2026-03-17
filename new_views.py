from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, FileResponse
from django.db.models import Count, Q, Sum, F
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.urls import reverse
from datetime import datetime, timedelta
import csv
import json
import os
import pandas as pd
import openpyxl
from pathlib import Path
import re
print("=== FEEDBACK ANALYSIS VIEW CALLED ===")
# Import models
from .models import (
    Training, Program, Faculty, TrainingAttendance, TrainingMetrics, 
    Hall, Schedule, MORUpload, Employee, ProgramScheduleDate, 
    Participant, ProgramDocument, TrainingAttendanceFile, 
    Attendance, DetailedSchedule, DetailedScheduleSnapshot,
    ScheduleDocument
)

# Import forms
from .forms import ExcelUploadForm, MORUploadForm

# Import decorators and auth helpers
from .decorators import (
    role_required, upload_download_required, edit_delete_required, 
    view_only_required, admin_required, alpha_required, beta_required
)
from .auth_views import get_user_role, can_upload_download, can_edit_delete, can_view_only
from .assessment_models import FeedbackExcelUpload
from .views import detect_column_categories

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def parse_time(t):
    """Parse time string to time object"""
    if not t:
        return None
    try:
        if isinstance(t, str):
            # Handle HH:MM format
            if ':' in t:
                return datetime.strptime(t, '%H:%M').time()
            # Handle HH:MM AM/PM format
            elif 'AM' in t.upper() or 'PM' in t.upper():
                return datetime.strptime(t, '%I:%M %p').time()
        return t
    except:
        return None

def parse_date(date_str):
    """Parse date string to date object"""
    if not date_str:
        return None
    try:
        if isinstance(date_str, str):
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        return date_str
    except:
        return None

# ============================================================================
# DASHBOARD & HOME VIEWS
# ============================================================================

@login_required
def home(request):
    """Dashboard home page - accessible to all authenticated users"""
    user_role = get_user_role(request.user)
    
    # Get program counts and details
    total_programs = Program.objects.count()
    Calendar_programs = Program.objects.filter(program_type='Calendar Program').count()
    Non_Calendar_programs = Program.objects.filter(program_type='Non Calendar Program').count()
    active_programs = Program.objects.filter(status='active').count()
    completed_programs = Program.objects.filter(status='completed').count()
    upcoming_programs = Program.objects.filter(status='upcoming').count()

    # Get training counts and details
    total_trainings = Training.objects.values('training_name').distinct().count()
    Calendar_trainings = Training.objects.filter(program_type='Calendar Program').values('training_name').distinct().count()
    Non_Calendar_trainings = Training.objects.filter(program_type='Non Calendar Program').values('training_name').distinct().count()
    current_month_trainings = Training.objects.filter(
        start_date__month=datetime.now().month,
        start_date__year=datetime.now().year
    ).values('training_name').distinct().count()
    
    # Get faculty counts and details
    total_faculty = Faculty.objects.count()
    active_faculty = Faculty.objects.filter(is_active=True).count()
    inactive_faculty = Faculty.objects.filter(is_active=False).count()
    faculty_by_dept = Training.objects.values('faculty_dept').annotate(
        count=Count('faculty_name', distinct=True)
    ).exclude(faculty_dept__isnull=True).exclude(faculty_dept__exact='')

    # Get participant counts and details
    total_participants = Participant.objects.count()
    monthly_participants = Participant.objects.filter(
        created_at__gte=datetime.now() - timedelta(days=30)
    ).count()
    participants_by_dept = Participant.objects.values('department').annotate(
        count=Count('id')
    ).exclude(department__isnull=True).exclude(department__exact='')

    # Get recent programs
    recent_programs = Program.objects.order_by('-created_at')[:5]

    # Get upcoming trainings
    upcoming_trainings = Training.objects.filter(
        start_date__gte=datetime.now().date()
    ).order_by('start_date')[:5]

    # Get schedule status counts
    planned_schedules = Schedule.objects.filter(status='Planned').count()
    cancelled_schedules = Schedule.objects.filter(status='Cancelled').count()
    completed_schedules = Schedule.objects.filter(status='Completed').count()
    postponed_schedules = Schedule.objects.filter(status='Postpone').count()

    # Get program schedule count
    total_program_schedules = Schedule.objects.count()

    context = {
        'user_role': user_role,
        # Program statistics
        'total_program_schedules': total_program_schedules,
        'Calendar_programs': Calendar_programs,
        'Non_Calendar_programs': Non_Calendar_programs,
        'active_programs': active_programs,
        'completed_programs': completed_programs,
        'upcoming_programs': upcoming_programs,
        # Schedule status counts
        'planned_schedules': planned_schedules,
        'cancelled_schedules': cancelled_schedules,
        'completed_schedules': completed_schedules,
        'postponed_schedules': postponed_schedules,
        
        # Training statistics
        'total_trainings': total_trainings,
        'Calendar_trainings': Calendar_trainings,
        'Non_Calendar_trainings': Non_Calendar_trainings,
        'current_month_trainings': current_month_trainings,
        
        # Faculty statistics
        'total_faculty': total_faculty,
        'active_faculty': active_faculty,
        'inactive_faculty': inactive_faculty,
        'faculty_by_dept': faculty_by_dept,
        
        # Participant statistics
        'total_participants': total_participants,
        'monthly_participants': monthly_participants,
        'participants_by_dept': participants_by_dept,
        
        # Lists
        'recent_programs': recent_programs,
        'upcoming_trainings': upcoming_trainings,
    }
    return render(request, 'dashboard/home.html', context)

# ============================================================================
# PROGRAM MANAGEMENT VIEWS
# ============================================================================

@login_required
def all_programs(request):
    """View all programs - accessible to all users"""
    programs = Program.objects.all().order_by('-created_at')
    
    # Pagination
    paginator = Paginator(programs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'programs': page_obj,
        'user_role': get_user_role(request.user),
        'can_edit': can_edit_delete(request.user),
    }
    return render(request, 'dashboard/all_programs.html', context)

@login_required
def calendar_programs(request):
    """View calendar programs - accessible to all users"""
    programs = Program.objects.filter(program_type='Calendar Program').order_by('-created_at')
    
    context = {
        'programs': programs,
        'user_role': get_user_role(request.user),
        'can_edit': can_edit_delete(request.user),
    }
    return render(request, 'dashboard/programs.html', context)

@login_required
def non_calendar_programs(request):
    """View non-calendar programs - accessible to all users"""
    programs = Program.objects.filter(program_type='Non Calendar Program').order_by('-created_at')
    
    context = {
        'programs': programs,
        'user_role': get_user_role(request.user),
        'can_edit': can_edit_delete(request.user),
    }
    return render(request, 'dashboard/programs.html', context)

@login_required
def program_details(request, program_id):
    """View program details - accessible to all users"""
    program = get_object_or_404(Program, id=program_id)
    trainings = program.trainings.all()
    
    context = {
        'program': program,
        'trainings': trainings,
        'user_role': get_user_role(request.user),
        'can_edit': can_edit_delete(request.user),
        'can_upload': can_upload_download(request.user),
    }
    return render(request, 'dashboard/program_details.html', context)

@edit_delete_required
@require_http_methods(["POST"])
def add_program(request):
    """Add new program - only admin and staff can edit"""
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            category = request.POST.get('category', 'SHE')
            description = request.POST.get('description', '')
            program_type = request.POST.get('program_type', 'Calendar Program')
            status = request.POST.get('status', 'Planned')
            
            program = Program.objects.create(
                name=name,
                category=category,
                description=description,
                program_type=program_type,
                status=status
            )
            
            messages.success(request, f'Program "{name}" created successfully!')
            return redirect('dashboard:program_details', program_id=program.id)
            
        except Exception as e:
            messages.error(request, f'Error creating program: {str(e)}')
            return redirect('dashboard:all_programs')
    
    return redirect('dashboard:all_programs')

@edit_delete_required
@require_http_methods(["POST"])
def update_program(request, program_id):
    """Update program - only admin and staff can edit"""
    program = get_object_or_404(Program, id=program_id)
    
    if request.method == 'POST':
        try:
            program.name = request.POST.get('name', program.name)
            program.category = request.POST.get('category', program.category)
            program.description = request.POST.get('description', program.description)
            program.program_type = request.POST.get('program_type', program.program_type)
            program.status = request.POST.get('status', program.status)
            program.save()
            
            messages.success(request, f'Program "{program.name}" updated successfully!')
            return redirect('dashboard:program_details', program_id=program.id)
            
        except Exception as e:
            messages.error(request, f'Error updating program: {str(e)}')
    
    return redirect('dashboard:program_details', program_id=program.id)

@admin_required
def delete_program(request, program_id):
    """Delete program - only admin can delete"""
    program = get_object_or_404(Program, id=program_id)
    
    try:
        program_name = program.name
        program.delete()
        messages.success(request, f'Program "{program_name}" deleted successfully!')
    except Exception as e:
        messages.error(request, f'Error deleting program: {str(e)}')
    
    return redirect('dashboard:all_programs')

# ============================================================================
# TRAINING MANAGEMENT VIEWS
# ============================================================================

@login_required
def training_details(request, training_id):
    """View training details - accessible to all users"""
    training = get_object_or_404(Training, id=training_id)
    faculty = training.faculty.all()
    attendance = training.attendance.first()
    metrics = training.metrics.first()
    
    context = {
        'training': training,
        'faculty': faculty,
        'attendance': attendance,
        'metrics': metrics,
        'user_role': get_user_role(request.user),
        'can_edit': can_edit_delete(request.user),
        'can_upload': can_upload_download(request.user),
    }
    return render(request, 'dashboard/training_details.html', context)

@edit_delete_required
@require_http_methods(["POST"])
def create_training(request):
    """Create new training - only admin and staff can edit"""
    if request.method == 'POST':
        try:
            program_id = request.POST.get('program_id')
            program = get_object_or_404(Program, id=program_id)
            
            training = Training.objects.create(
                program_type=request.POST.get('program_type', 'Calendar Program'),
                training_name=request.POST.get('training_name'),
                medium=request.POST.get('medium', ''),
                psi_Non_psi=request.POST.get('psi_Non_psi', ''),
                area=request.POST.get('area', ''),
                month=request.POST.get('month', ''),
                start_date=request.POST.get('start_date'),
                end_date=request.POST.get('end_date'),
                start_time=request.POST.get('start_time'),
                end_time=request.POST.get('end_time'),
                hours=request.POST.get('hours', 0),
                faculty_t_no=request.POST.get('faculty_t_no', ''),
                faculty_name=request.POST.get('faculty_name', ''),
                faculty_dept=request.POST.get('faculty_dept', ''),
                gender=request.POST.get('gender', ''),
                trainee_name=request.POST.get('trainee_name', ''),
                program=program,
                content=request.POST.get('content', ''),
                benefits=request.POST.get('benefits', '')
            )
            
            messages.success(request, f'Training "{training.training_name}" created successfully!')
            return redirect('dashboard:training_details', training_id=training.id)
            
        except Exception as e:
            messages.error(request, f'Error creating training: {str(e)}')
            return redirect('dashboard:all_programs')
    
    return redirect('dashboard:all_programs')

@edit_delete_required
@require_http_methods(["POST"])
def update_training(request, training_id):
    """Update training - only admin and staff can edit"""
    training = get_object_or_404(Training, id=training_id)
    
    if request.method == 'POST':
        try:
            training.training_name = request.POST.get('training_name', training.training_name)
            training.medium = request.POST.get('medium', training.medium)
            training.psi_Non_psi = request.POST.get('psi_Non_psi', training.psi_Non_psi)
            training.area = request.POST.get('area', training.area)
            training.month = request.POST.get('month', training.month)
            training.start_date = request.POST.get('start_date', training.start_date)
            training.end_date = request.POST.get('end_date', training.end_date)
            training.start_time = request.POST.get('start_time', training.start_time)
            training.end_time = request.POST.get('end_time', training.end_time)
            training.hours = request.POST.get('hours', training.hours)
            training.faculty_t_no = request.POST.get('faculty_t_no', training.faculty_t_no)
            training.faculty_name = request.POST.get('faculty_name', training.faculty_name)
            training.faculty_dept = request.POST.get('faculty_dept', training.faculty_dept)
            training.gender = request.POST.get('gender', training.gender)
            training.trainee_name = request.POST.get('trainee_name', training.trainee_name)
            training.content = request.POST.get('content', training.content)
            training.benefits = request.POST.get('benefits', training.benefits)
            training.save()
            
            messages.success(request, f'Training "{training.training_name}" updated successfully!')
            return redirect('dashboard:training_details', training_id=training.id)
            
        except Exception as e:
            messages.error(request, f'Error updating training: {str(e)}')
    
    return redirect('dashboard:training_details', training_id=training.id)

@admin_required
def delete_training(request, training_id):
    """Delete training - only admin can delete"""
    training = get_object_or_404(Training, id=training_id)
    
    try:
        training_name = training.training_name
        training.delete()
        messages.success(request, f'Training "{training_name}" deleted successfully!')
    except Exception as e:
        messages.error(request, f'Error deleting training: {str(e)}')
    
    return redirect('dashboard:all_programs')

# ============================================================================
# FACULTY MANAGEMENT VIEWS
# ============================================================================

@login_required
def faculty_list(request):
    """View faculty list - accessible to all users"""
    faculty = Faculty.objects.all().order_by('name')
    
    # Pagination
    paginator = Paginator(faculty, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'faculty': page_obj,
        'user_role': get_user_role(request.user),
        'can_edit': can_edit_delete(request.user),
    }
    return render(request, 'dashboard/faculty_list.html', context)

@edit_delete_required
@require_http_methods(["POST"])
def add_faculty(request, training_id):
    """Add faculty to training - only admin and staff can edit"""
    training = get_object_or_404(Training, id=training_id)
    
    if request.method == 'POST':
        try:
            faculty_name = request.POST.get('faculty_name')
            faculty_dept = request.POST.get('faculty_dept')
            faculty_t_no = request.POST.get('faculty_t_no')
            
            # Create or get faculty
            faculty, created = Faculty.objects.get_or_create(
                faculty_t_no=faculty_t_no,
                defaults={
                    'name': faculty_name,
                    'faculty_dept': faculty_dept,
                }
            )
            
            # Add to training
            training.faculty.add(faculty)
            
            messages.success(request, f'Faculty "{faculty_name}" added to training successfully!')
            
        except Exception as e:
            messages.error(request, f'Error adding faculty: {str(e)}')
    
    return redirect('dashboard:training_details', training_id=training.id)

@edit_delete_required
@require_http_methods(["POST"])
def edit_faculty(request, faculty_id):
    """Edit faculty - only admin and staff can edit"""
    faculty = get_object_or_404(Faculty, id=faculty_id)
    
    if request.method == 'POST':
        try:
            faculty.name = request.POST.get('name', faculty.name)
            faculty.faculty_dept = request.POST.get('faculty_dept', faculty.faculty_dept)
            faculty.faculty_t_no = request.POST.get('faculty_t_no', faculty.faculty_t_no)
            faculty.email = request.POST.get('email', faculty.email)
            faculty.phone = request.POST.get('phone', faculty.phone)
            faculty.is_active = request.POST.get('is_active') == 'on'
            faculty.save()
            
            messages.success(request, f'Faculty "{faculty.name}" updated successfully!')
            
        except Exception as e:
            messages.error(request, f'Error updating faculty: {str(e)}')
    
    return redirect('dashboard:faculty_list')

@edit_delete_required
def remove_faculty(request, faculty_id):
    """Remove faculty from training - only admin and staff can edit"""
    faculty = get_object_or_404(Faculty, id=faculty_id)
    training_id = request.GET.get('training_id')
    
    if training_id:
        training = get_object_or_404(Training, id=training_id)
        training.faculty.remove(faculty)
        messages.success(request, f'Faculty "{faculty.name}" removed from training successfully!')
        return redirect('dashboard:training_details', training_id=training_id)
    
    return redirect('dashboard:faculty_list')

# ============================================================================
# FILE UPLOAD & DOWNLOAD VIEWS
# ============================================================================

@upload_download_required
def upload_excel(request):
    """Upload Excel file - only admin and User Alpha can upload"""
    if request.method == 'POST':
        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                excel_file = request.FILES['file']
                
                # Save file
                file_path = os.path.join('media', 'excel_files', excel_file.name)
                with open(file_path, 'wb+') as destination:
                    for chunk in excel_file.chunks():
                        destination.write(chunk)
                
                # Process file (you can add your Excel processing logic here)
                messages.success(request, f'File "{excel_file.name}" uploaded successfully!')
                
            except Exception as e:
                messages.error(request, f'Error uploading file: {str(e)}')
        else:
            messages.error(request, 'Invalid file format. Please upload an Excel file.')
    
    form = ExcelUploadForm()
    context = {
        'form': form,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'dashboard/upload_excel.html', context)

@upload_download_required
def uploaded_files(request):
    """View uploaded files - only admin and User Alpha can access"""
    files_dir = Path('media/excel_files')
    files = []
    
    if files_dir.exists():
        for file_path in files_dir.glob('*.xlsx'):
            files.append({
                'name': file_path.name,
                'size': file_path.stat().st_size,
                'modified': datetime.fromtimestamp(file_path.stat().st_mtime)
            })
    
    context = {
        'files': files,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'dashboard/uploaded_files.html', context)

@upload_download_required
def download_file(request, filename):
    """Download file - only admin and User Alpha can download"""
    file_path = os.path.join('media', 'excel_files', filename)
    
    if os.path.exists(file_path):
        with open(file_path, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
    else:
        messages.error(request, 'File not found.')
        return redirect('dashboard:uploaded_files')

@admin_required
def delete_uploaded_file(request, filename):
    """Delete uploaded file - only admin can delete"""
    file_path = os.path.join('media', 'excel_files', filename)
    
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            messages.success(request, f'File "{filename}" deleted successfully!')
        except Exception as e:
            messages.error(request, f'Error deleting file: {str(e)}')
    else:
        messages.error(request, 'File not found.')
    
    return redirect('dashboard:uploaded_files')

# ============================================================================
# SCHEDULING VIEWS
# ============================================================================

@login_required
def calendar_view(request):
    """Calendar view - accessible to all users"""
    schedules = Schedule.objects.all().order_by('date')
    
    context = {
        'schedules': schedules,
        'user_role': get_user_role(request.user),
        'can_edit': can_edit_delete(request.user),
        'is_alpha': get_user_role(request.user) == 'alpha',
        'is_beta': get_user_role(request.user) == 'beta',
    }
    return render(request, 'dashboard/scheduling.html', context)

@edit_delete_required
@require_http_methods(["POST"])
def create_schedule(request):
    """Create schedule - only admin and staff can edit"""
    if request.method == 'POST':
        try:
            program_id = request.POST.get('program_id')
            program = get_object_or_404(Program, id=program_id)
            
            schedule = Schedule.objects.create(
                program=program,
                date=request.POST.get('date'),
                start_time=request.POST.get('start_time'),
                end_time=request.POST.get('end_time'),
                duration=request.POST.get('duration'),
                students=request.POST.get('students'),
                equipment=request.POST.get('equipment', ''),
                status=request.POST.get('status', 'Planned')
            )
            
            messages.success(request, 'Schedule created successfully!')
            return redirect('dashboard:calendar_view')
            
        except Exception as e:
            messages.error(request, f'Error creating schedule: {str(e)}')
    
    return redirect('dashboard:calendar_view')

@edit_delete_required
@require_http_methods(["POST"])
def update_schedule(request, schedule_id):
    """Update schedule - only admin and staff can edit"""
    schedule = get_object_or_404(Schedule, id=schedule_id)
    
    if request.method == 'POST':
        try:
            schedule.date = request.POST.get('date', schedule.date)
            schedule.start_time = request.POST.get('start_time', schedule.start_time)
            schedule.end_time = request.POST.get('end_time', schedule.end_time)
            schedule.duration = request.POST.get('duration', schedule.duration)
            schedule.students = request.POST.get('students', schedule.students)
            schedule.equipment = request.POST.get('equipment', schedule.equipment)
            schedule.status = request.POST.get('status', schedule.status)
            schedule.save()
            
            messages.success(request, 'Schedule updated successfully!')
            
        except Exception as e:
            messages.error(request, f'Error updating schedule: {str(e)}')
    
    return redirect('dashboard:calendar_view')

@admin_required
def delete_schedule(request, schedule_id):
    """Delete schedule - only admin can delete"""
    schedule = get_object_or_404(Schedule, id=schedule_id)
    
    try:
        schedule.delete()
        messages.success(request, 'Schedule deleted successfully!')
    except Exception as e:
        messages.error(request, f'Error deleting schedule: {str(e)}')
    
    return redirect('dashboard:calendar_view')

# ============================================================================
# API VIEWS
# ============================================================================

@login_required
@csrf_exempt
def api_programs(request):
    """API endpoint for programs - accessible to all users"""
    programs = Program.objects.all()
    data = []
    
    for program in programs:
        data.append({
            'id': program.id,
            'name': program.name,
            'category': program.category,
            'program_type': program.program_type,
            'status': program.status,
            'created_at': program.created_at.isoformat(),
        })
    
    return JsonResponse(data, safe=False)

@login_required
@csrf_exempt
def api_trainings(request):
    """API endpoint for trainings - accessible to all users"""
    trainings = Training.objects.all().select_related('program')
    program_id = request.GET.get('program_id')
    category = request.GET.get('category')
    if program_id:
        trainings = trainings.filter(program_id=program_id)
    if category:
        trainings = trainings.filter(program__category__iexact=category)
    trainings = trainings.order_by('program__category', 'training_name')
    data = []
    for training in trainings:
        data.append({
            'id': training.id,
            'training_name': training.training_name,
        })
    return JsonResponse(data, safe=False)

@login_required
@csrf_exempt
def api_faculty(request):
    """API endpoint for faculty - accessible to all users"""
    if request.method == 'GET':
        try:
            # Return all unique departments if requested
            if request.GET.get('all_departments') == '1':
                depts = Faculty.objects.values_list('faculty_dept', flat=True).distinct()
                return JsonResponse(list(filter(None, depts)), safe=False)
            
            # Return all unique genders if requested
            if request.GET.get('all_genders') == '1':
                genders = Faculty.objects.values_list('gender_key', flat=True).distinct()
                return JsonResponse(list(filter(None, genders)), safe=False)
            
            # Get search parameter
            search = request.GET.get('search', '').strip()
            faculty = Faculty.objects.all()
            
            # Filter by department if provided
            faculty_dept = request.GET.get('faculty_dept')
            if faculty_dept:
                faculty = faculty.filter(faculty_dept=faculty_dept)
            
            # Filter by gender if provided (use gender_key field)
            gender = request.GET.get('gender')
            if gender:
                faculty = faculty.filter(gender_key=gender)
            
            # Apply search filter if search term exists
            if search:
                words = search.split()
                for word in words:
                    faculty = faculty.filter(name__icontains=word)
                # Still allow search by t_no or dept as before
                faculty = faculty | Faculty.objects.filter(
                    Q(faculty_t_no__icontains=search) |
                    Q(faculty_dept__icontains=search)
                )
            
            faculty = faculty.order_by('name')
            data = []
            
            for f in faculty:
                data.append({
                    'id': f.id,
                    'name': f.name,
                    'faculty_dept': f.faculty_dept,
                    'faculty_t_no': f.faculty_t_no,
                    'email': f.email,
                    'phone': f.phone,
                    'gender_key': getattr(f, 'gender_key', None),
                    'is_active': f.is_active,
                })
            
            return JsonResponse(data, safe=False)
            
        except Exception as e:
            print(f"Error in api_faculty GET: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    elif request.method == 'POST':
        if not request.headers.get('X-CSRFToken'):
            return JsonResponse({'error': 'CSRF token missing'}, status=403)
        try:
            data = json.loads(request.body)
            
            # Check if faculty with this Pers.No already exists
            faculty_t_no = data.get('faculty_t_no', '').strip()
            name = data.get('name', '').strip()
            faculty_dept = data.get('faculty_dept', '').strip()
            
            if not name or not faculty_dept:
                return JsonResponse({
                    'success': False,
                    'error': 'Name and Department are required fields'
                }, status=400)
            
            # Try to find existing faculty by T.No or name+dept combination
            existing_faculty = None
            if faculty_t_no:
                existing_faculty = Faculty.objects.filter(faculty_t_no=faculty_t_no).first()
            if not existing_faculty:
                existing_faculty = Faculty.objects.filter(
                    name=name,
                    faculty_dept=faculty_dept
                ).first()
            
            if existing_faculty:
                # Update existing faculty
                existing_faculty.name = name
                existing_faculty.faculty_dept = faculty_dept
                if faculty_t_no:
                    existing_faculty.faculty_t_no = faculty_t_no
                existing_faculty.email = data.get('email', existing_faculty.email)
                existing_faculty.phone = data.get('phone', existing_faculty.phone)
                existing_faculty.save()
                
                return JsonResponse({
                    'success': True, 
                    'faculty': {
                        'id': existing_faculty.id,
                        'name': existing_faculty.name,
                        'faculty_dept': existing_faculty.faculty_dept,
                        'faculty_t_no': existing_faculty.faculty_t_no,
                        'email': existing_faculty.email,
                        'phone': existing_faculty.phone
                    }
                })
            else:
                # Create new faculty
                faculty = Faculty.objects.create(
                    name=name,
                    faculty_dept=faculty_dept,
                    faculty_t_no=faculty_t_no,
                    email=data.get('email', ''),
                    phone=data.get('phone', '')
                )
                return JsonResponse({
                    'success': True, 
                    'faculty': {
                        'id': faculty.id,
                        'name': faculty.name,
                        'faculty_dept': faculty.faculty_dept,
                        'faculty_t_no': faculty.faculty_t_no,
                        'email': faculty.email,
                        'phone': faculty.phone
                    }
                })
        except Exception as e:
            print(f"Error in faculty creation/update: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)})
    else:
        return JsonResponse({'error': 'Invalid method'}, status=405)

@login_required
@csrf_exempt
def api_schedules(request):
    """API endpoint for schedules - accessible to all users"""
    try:
        # Get filter parameters
        program_type = request.GET.get('program_type', 'all')
        program_id = request.GET.get('program_id')
        training_id = request.GET.get('training_id')
        date = request.GET.get('date')
        month = request.GET.get('month')
        year = request.GET.get('year')
        
        # Base queryset
        schedules = Schedule.objects.select_related(
            'program', 'faculty', 'alt_faculty', 'hall', 'training'
        ).prefetch_related('training__faculty').all()
        
        # Apply filters
        if program_type != 'all':
            schedules = schedules.filter(training__program_type=program_type)
        if program_id:
            schedules = schedules.filter(program_id=program_id)
        if training_id:
            schedules = schedules.filter(training_id=training_id)
        if date:
            try:
                from datetime import datetime
                date_obj = datetime.strptime(date, '%Y-%m-%d').date()
                schedules = schedules.filter(date=date_obj)
            except ValueError:
                return JsonResponse({'error': 'Invalid date format'}, status=400)
        
        # Apply month and year filtering for status counts
        status_schedules = schedules
        if month and year:
            try:
                month_int = int(month)
                year_int = int(year)
                status_schedules = schedules.filter(
                    date__year=year_int,
                    date__month=month_int
                )
            except ValueError:
                return JsonResponse({'error': 'Invalid month or year format'}, status=400)
        
        schedule_data = []
        status_counts = {'Planned': 0, 'Completed': 0, 'Cancelled': 0, 'Postponed': 0}
        
        # Count statuses for the filtered month
        for schedule in status_schedules:
            status = (schedule.status or '').capitalize()
            if status == 'Postpone':
                status = 'Postponed'
            if status in status_counts:
                status_counts[status] += 1
        
        # Process all schedules for the main data
        for schedule in schedules:
            # Get faculty name and ID
            faculty_name = schedule.faculty.name if schedule.faculty else 'N/A'
            faculty_id = schedule.faculty.id if schedule.faculty else None
            
            # Get faculty P No.s
            faculty_pnos = []
            if schedule.training:
                for faculty in schedule.training.faculty.all():
                    # First try to get P No. from Employee model
                    fac_tno = (faculty.faculty_t_no or '').strip().upper()
                    emp = Employee.objects.filter(pers_no__iexact=fac_tno).first() if fac_tno else None
                    
                    # Use Employee P No. if available, otherwise use faculty_t_no, or 'N/A'
                    p_no = emp.pers_no if emp and emp.pers_no else fac_tno if fac_tno else 'N/A'
                    if p_no != 'N/A':  # Only add non-N/A P No.s
                        faculty_pnos.append(p_no)
            
            # If no valid P No.s found, use 'N/A'
            if not faculty_pnos:
                faculty_pnos = ['N/A']
            
            schedule_data.append({
                'id': schedule.id,
                'program': schedule.program.name if schedule.program else '',
                'program_id': schedule.program.id if schedule.program else None,
                'program_category': schedule.program.category if schedule.program else '',
                'program_type': schedule.program_type if hasattr(schedule, 'program_type') and schedule.program_type else 'Calendar Program',
                'training_id': schedule.training.id if schedule.training else None,
                'training_name': schedule.training.training_name if schedule.training else '',
                'faculty': faculty_name,
                'faculty_id': faculty_id,
                'department': schedule.faculty.faculty_dept if schedule.faculty else 'N/A',
                'faculty_gender': schedule.faculty.gender_key if schedule.faculty else 'N/A',
                'hall': schedule.hall.name if schedule.hall else '',
                'hall_id': schedule.hall.id if schedule.hall else None,
                'hall_capacity': schedule.hall.capacity if schedule.hall and hasattr(schedule.hall, 'capacity') else 'N/A',
                'date': schedule.date.strftime('%Y-%m-%d') if schedule.date else None,
                'end_date': schedule.end_date.strftime('%Y-%m-%d') if hasattr(schedule, 'end_date') and schedule.end_date else '',
                'start_time': schedule.start_time.strftime('%H:%M') if schedule.start_time else '',
                'end_time': schedule.end_time.strftime('%H:%M') if hasattr(schedule, 'end_time') and schedule.end_time else '',
                'duration': int(schedule.duration) if schedule.duration is not None else None,
                'students': schedule.students,
                'equipment': schedule.equipment,
                'status': schedule.status,
                'notified_status': schedule.notified_status,
                'occupancy': f"{schedule.students}/{schedule.hall.capacity} ({int((schedule.students/schedule.hall.capacity)*100)}%)" if schedule.hall and schedule.hall.capacity and schedule.students else '',
                'faculty_t_nos': faculty_pnos,  # Use the collected faculty P No.s
                'faculty_alt': schedule.alt_faculty.name if schedule.alt_faculty else 'N/A',
                'p_no_alt': schedule.alt_faculty.faculty_t_no if schedule.alt_faculty else 'N/A',
                'alt_faculty_gender': schedule.alt_faculty.gender_key if schedule.alt_faculty else 'N/A',
                'notified_unnotified': schedule.notified_status if schedule.notified_status else 'N/A'
            })
        
        return JsonResponse({'schedules': schedule_data, 'status_counts': status_counts}, safe=False)
        
    except Exception as e:
        import traceback
        print(f"Error in api_schedules: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=500)

# ============================================================================
# UTILITY VIEWS
# ============================================================================

@login_required
def dashboard_data(request):
    """Dashboard data API - accessible to all users"""
    user_role = get_user_role(request.user)
    
    data = {
        'user_role': user_role,
        'can_edit': can_edit_delete(request.user),
        'can_upload': can_upload_download(request.user),
        'can_view_only': can_view_only(request.user),
        'total_programs': Program.objects.count(),
        'total_trainings': Training.objects.count(),
        'total_faculty': Faculty.objects.count(),
        'total_participants': Participant.objects.count(),
    }
    
    return JsonResponse(data)

@login_required
def search(request):
    """Search functionality - accessible to all users"""
    query = request.GET.get('q', '')
    results = []
    
    if query:
        # Search in programs
        programs = Program.objects.filter(name__icontains=query)
        for program in programs:
            results.append({
                'type': 'Program',
                'name': program.name,
                'url': reverse('dashboard:program_details', args=[program.id])
            })
        
        # Search in trainings
        trainings = Training.objects.filter(training_name__icontains=query)
        for training in trainings:
            results.append({
                'type': 'Training',
                'name': training.training_name,
                'url': reverse('dashboard:training_details', args=[training.id])
            })
        
        # Search in faculty
        faculty = Faculty.objects.filter(name__icontains=query)
        for f in faculty:
            results.append({
                'type': 'Faculty',
                'name': f.name,
                'url': '#'
            })
    
    context = {
        'query': query,
        'results': results,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'dashboard/search.html', context)
# ============================================================================
# MISSING VIEWS (Add these before the error handlers)
# ============================================================================

@upload_download_required
def sync_onedrive(request):
    """Sync OneDrive - only admin and User Alpha can access"""
    # Add your OneDrive sync logic here
    messages.success(request, 'OneDrive sync completed successfully!')
    return redirect('dashboard:dashboard-home')

@upload_download_required
def edit_excel(request, filename):
    """Edit Excel file - only admin and User Alpha can access"""
    context = {
        'filename': filename,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'dashboard/edit_excel.html', context)

@login_required
def generate_report(request, program_id):
    """Generate report - accessible to all users"""
    program = get_object_or_404(Program, id=program_id)
    context = {
        'program': program,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'dashboard/generate_report.html', context)

@edit_delete_required
@require_http_methods(["POST"])
def update_training(request, training_id):
    """Update training - only admin and staff can edit"""
    return update_training(request, training_id)

@edit_delete_required
@require_http_methods(["POST"])
def update_training_content(request, training_id):
    """Update training content - only admin and staff can edit"""
    training = get_object_or_404(Training, id=training_id)
    if request.method == 'POST':
        training.content = request.POST.get('content', '')
        training.save()
        messages.success(request, 'Training content updated successfully!')
    return redirect('dashboard:training_details', training_id=training.id)

@edit_delete_required
@require_http_methods(["POST"])
def update_training_benefits(request, training_id):
    """Update training benefits - only admin and staff can edit"""
    training = get_object_or_404(Training, id=training_id)
    if request.method == 'POST':
        training.benefits = request.POST.get('benefits', '')
        training.save()
        messages.success(request, 'Training benefits updated successfully!')
    return redirect('dashboard:training_details', training_id=training.id)

@edit_delete_required
def edit_training(request, training_id):
    """Edit training - only admin and staff can edit"""
    training = get_object_or_404(Training, id=training_id)
    context = {
        'training': training,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'dashboard/edit_training.html', context)

@admin_required
def delete_training(request, training_id):
    """Delete training - only admin can delete"""
    training = get_object_or_404(Training, id=training_id)
    training.delete()
    messages.success(request, 'Training deleted successfully!')
    return redirect('dashboard:all_programs')

@upload_download_required
def mor_upload(request):
    """MOR upload - only admin and User Alpha can access"""
    if request.method == 'POST':
        form = MORUploadForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'MOR file uploaded successfully!')
            return redirect('dashboard:mor_list')
    else:
        form = MORUploadForm()
    
    context = {
        'form': form,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'dashboard/mor_upload.html', context)

@login_required
def mor_list(request):
    """MOR list - accessible to all users"""
    mor_uploads = MORUpload.objects.all().order_by('-upload_date')
    context = {
        'mor_uploads': mor_uploads,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'dashboard/mor_list.html', context)

@login_required
@csrf_exempt
def schedule_trainings(request):
    """Schedule trainings - accessible to all users except User Beta"""
    # Check if user is User Beta - deny access
    user_role = get_user_role(request.user)
    if user_role == 'beta':
        messages.error(request, 'User Beta does not have access to schedule trainings.')
        return redirect('dashboard:dashboard-home')
    
    try:
        # Get program ID from query parameters
        program_id = request.GET.get('program_id')
        if not program_id:
            return JsonResponse({'error': 'Program ID is required'}, status=400)
        
        try:
            program = Program.objects.get(id=program_id)
        except Program.DoesNotExist:
            print("Debug - Program not found, redirecting to calendar")
            return JsonResponse({'error': 'Program not found'}, status=404)
        
        # Get training IDs from query parameters
        training_ids = request.GET.get('trainings', '')
        if not training_ids:
            return JsonResponse({'error': 'Training IDs are required'}, status=400)
        
        # Parse training IDs
        training_id_list = [int(tid.strip()) for tid in training_ids.split(',') if tid.strip()]
        selected_trainings = Training.objects.filter(id__in=training_id_list)
        
        # Get faculty and halls for the form
        faculty = Faculty.objects.filter(is_active=True).order_by('name')
        halls = Hall.objects.all().order_by('name')
        
        # Get selected date from query parameters or use today
        selected_date_str = request.GET.get('selected_date')
        if selected_date_str:
            try:
                default_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            except ValueError:
                default_date = datetime.now().date()
        else:
            default_date = datetime.now().date()
        
        # Get existing schedules for these trainings and date
        existing_schedules = Schedule.objects.filter(
            training__in=selected_trainings,
            date=default_date
        ).select_related('training', 'faculty', 'hall')
        
      
        
        # Convert to list for template
        existing_schedules_list = []
        for schedule in existing_schedules:
            schedule_docs = ScheduleDocument.objects.filter(schedule=schedule)
            documents = [
                {'id': doc.id, 'url': doc.document.url, 'name': os.path.basename(doc.document.name)}
                for doc in schedule_docs
            ]
            existing_schedules_list.append({
                'id': schedule.id,
                'training_id': schedule.training.id,
                'training_name': schedule.training.training_name,
                'date': schedule.date.strftime('%Y-%m-%d') if schedule.date else None,
                'start_time': schedule.start_time.strftime('%H:%M') if schedule.start_time else None,
                'end_time': schedule.end_time.strftime('%H:%M') if schedule.end_time else None,
                'duration': schedule.duration,
                'faculty_id': schedule.faculty.id if schedule.faculty else None,
                'faculty_name': schedule.faculty.name if schedule.faculty else None,
                'hall_id': schedule.hall.id if schedule.hall else None,
                'hall_name': schedule.hall.name if schedule.hall else None,
                'students': schedule.students,
                'equipment': schedule.equipment,
                'status': schedule.status,
                'documents': documents,  # Add documents to the dict
            })
        
        # When attaching schedule_for_selected_date to each training, also attach documents as a custom attribute
        for training in selected_trainings:
            sched = next((s for s in existing_schedules if s.training.id == training.id), None)
            if sched:
                training.schedule_for_selected_date = sched
                schedule_docs = ScheduleDocument.objects.filter(schedule=sched)
                training.schedule_for_selected_date.docs_for_template = [
                    {'id': doc.id, 'url': doc.document.url, 'name': os.path.basename(doc.document.name)}
                    for doc in schedule_docs
                ]
            else:
                training.schedule_for_selected_date = None
        
        # Convert to JSON for JavaScript
        import json
        existing_schedules_json = json.dumps(existing_schedules_list)
        
        # Return HTML template for regular requests
        context = {
            'program': program,
            'trainings': selected_trainings,
            'faculty': faculty,
            'halls': halls,
            'selected_date': default_date.strftime('%Y-%m-%d'),
            'existing_schedules': existing_schedules_list,  # For template rendering
            'existing_schedules_json': existing_schedules_json,  # For JS
            'default_start_date': default_date,
            'default_end_date': default_date,
            'scheduleData': existing_schedules_list,  # Add this line for FullCalendar
            'user_role': user_role,
            'can_edit': can_edit_delete(request.user),
            'can_upload_download': can_upload_download(request.user),
            'is_admin': request.user.is_superuser or request.user.is_staff,
            'is_alpha': user_role == 'alpha',
            'is_beta': user_role == 'beta',
        }
        
        return render(request, 'dashboard/schedule_trainings.html', context)
        
    except Exception as e:
        print(f"Debug - Error in schedule_trainings: {str(e)}")
        import traceback
        print(traceback.format_exc())
        # Return a JSON error response
        return JsonResponse({
            'error': 'An error occurred while loading the schedule page',
            'details': str(e)
        }, status=500)

# API endpoints
@login_required
@csrf_exempt
def api_schedules_batch(request):
    """API for batch schedule operations - accessible to all users"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            program_id = data.get('program_id')
            schedules_data = data.get('schedules', [])
            
            if not program_id:
                return JsonResponse({'success': False, 'error': 'Program ID is required'}, status=400)
            
            try:
                program = Program.objects.get(id=program_id)
            except Program.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Program not found'}, status=404)
            
            saved_schedules = []
            
            for sched in schedules_data:
                try:
                    # Get training
                    training_id = sched.get('training_id')
                    if not training_id:
                        print('[DEBUG] Missing training_id in schedule:', sched)
                        continue
                    
                    try:
                        training = Training.objects.get(id=training_id)
                    except Training.DoesNotExist:
                        print('[DEBUG] Training not found:', training_id)
                        continue

                    # Parse dates
                    date = parse_date(sched.get('date'))
                    end_date = parse_date(sched.get('end_date')) if sched.get('end_date') else None
                    
                    if not date:
                        print('[DEBUG] Invalid date in schedule:', sched)
                        continue

                    # Parse times
                    st = parse_time(sched.get('start_time'))
                    et = parse_time(sched.get('end_time'))
                    
                    # Get faculty
                    faculty_ids = sched.get('faculty_ids', [])
                    faculty = None
                    if faculty_ids:
                        try:
                            faculty = Faculty.objects.get(id=faculty_ids[0])
                            # Update training's faculty
                            training.faculty.clear()
                            for fid in faculty_ids:
                                try:
                                    f = Faculty.objects.get(id=fid)
                                    training.faculty.add(f)
                                except Faculty.DoesNotExist:
                                    continue
                        except Faculty.DoesNotExist:
                            print('[DEBUG] Faculty not found:', faculty_ids[0])
                            continue
                    
                    # Get hall
                    hall = None
                    if sched.get('hall_id'):
                        try:
                            hall = Hall.objects.get(id=sched.get('hall_id'))
                        except Hall.DoesNotExist:
                            print('[DEBUG] Hall not found:', sched.get('hall_id'))
                            continue
                    
                    # Check if schedule already exists
                    existing_schedule = Schedule.objects.filter(
                        program=program,
                        training=training,
                        date=date
                    ).first()
                    
                    if existing_schedule:
                        # Update existing schedule
                        existing_schedule.program = program
                        existing_schedule.training = training
                        existing_schedule.faculty = faculty
                        existing_schedule.hall = hall
                        existing_schedule.date = date
                        existing_schedule.start_time = st
                        existing_schedule.end_time = et
                        existing_schedule.duration = int(sched.get('duration')) if sched.get('duration') else None
                        existing_schedule.students = int(sched.get('students')) if sched.get('students') else None
                        existing_schedule.equipment = sched.get('equipment', '')
                        existing_schedule.status = sched.get('status', 'Planned')
                        existing_schedule.end_date = end_date or date
                        existing_schedule.save()
                        schedule = existing_schedule
                    else:
                        # Create new schedule
                        schedule = Schedule.objects.create(
                            program=program,
                            training=training,
                            faculty=faculty,
                            hall=hall,
                            date=date,
                            start_time=st,
                            end_time=et,
                            duration=int(sched.get('duration')) if sched.get('duration') else None,
                            students=int(sched.get('students')) if sched.get('students') else None,
                            equipment=sched.get('equipment', ''),
                            status=sched.get('status', 'Planned'),
                            end_date=end_date or date
                        )
                    
                    saved_schedules.append(schedule)
                    
                except Exception as e:
                    print('[DEBUG] Error saving schedule:', str(e))
                    continue
            
            if not saved_schedules:
                return JsonResponse({
                    'success': False,
                    'error': 'No schedules were saved. Please check the data and try again.'
                }, status=400)

            return JsonResponse({
                'success': True,
                'message': f'Successfully saved {len(saved_schedules)} schedules',
                'schedules': [{
                    'id': s.id,
                    'training_id': s.training.id if s.training else None,
                    'faculty_ids': list(s.training.faculty.values_list('id', flat=True)) if s.training else [],
                    'hall_id': s.hall.id if s.hall else None,
                    'date': s.date.isoformat() if s.date else None,
                    'start_time': s.start_time.strftime('%H:%M') if s.start_time else None,
                    'end_time': s.end_time.strftime('%H:%M') if s.end_time else None,
                    'students': s.students,
                    'status': s.status
                } for s in saved_schedules]
            })

        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            print('[DEBUG] Unexpected error in api_schedules_batch:', str(e))
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

@login_required
@csrf_exempt
def api_halls(request):
    """API for halls"""
    halls = Hall.objects.all()
    data = [{'id': h.id, 'name': h.name, 'capacity': h.capacity} for h in halls]
    return JsonResponse({'halls': data})

@login_required
@csrf_exempt
def api_faculty_detail(request, faculty_id):
    """API for faculty detail"""
    faculty = get_object_or_404(Faculty, id=faculty_id)
    data = {
        'id': faculty.id,
        'name': faculty.name,
        'faculty_dept': faculty.faculty_dept,
        'faculty_t_no': faculty.faculty_t_no,
        'email': faculty.email,
        'is_active': faculty.is_active,
    }
    return JsonResponse(data)

@login_required
@csrf_exempt
def api_program_dates_create(request):
    """API for creating program dates"""
    return JsonResponse({'status': 'success'})

@login_required
@csrf_exempt
def api_program_dates_update(request, sched_id):
    """API for updating program dates"""
    return JsonResponse({'status': 'success'})

@login_required
@csrf_exempt
def api_program_dates_delete(request, sched_id):
    """API for deleting program dates"""
    return JsonResponse({'status': 'success'})

@login_required
@csrf_exempt
def api_verify_sync(request):
    """API for verifying sync"""
    return JsonResponse({'status': 'success'})

@csrf_exempt
def api_schedule_upload_excel(request, schedule_id):
    """API for uploading schedule Excel (feedback, pre, post) with correct JSON response."""
    from django.http import JsonResponse
    from django.core.files.storage import FileSystemStorage
    from django.conf import settings
    import os
    import pandas as pd
    import re
    from .models import Schedule, Training
    from .assessment_models import FeedbackExcelUpload
    from django.utils import timezone
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    try:
        schedule = Schedule.objects.get(id=schedule_id)
    except Schedule.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Schedule not found'}, status=404)
    file = request.FILES.get('file')
    category = request.POST.get('category') or request.GET.get('category')
    valid_categories = ['feedback', 'pre', 'post']
    if not category or category not in valid_categories:
        return JsonResponse({'success': False, 'error': f"Invalid or missing category. Must be one of: {', '.join(valid_categories)}"}, status=400)
    if not file:
        return JsonResponse({'success': False, 'error': 'No file uploaded'})
    if not file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'success': False, 'error': 'Please upload an Excel file'})
    try:
        fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'feedback_excel'))
        filename = fs.save(f"schedule_{schedule_id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}_{file.name}", file)
        # Extract English columns for admin model
        def extract_english(col):
            match = re.search(r'\(([^)]+)\)', col)
            return match.group(1).strip() if match else col
        try:
            df = pd.read_excel(fs.path(filename))
            english_columns = [extract_english(col) for col in df.columns]
        except Exception:
            english_columns = []
        FeedbackExcelUpload.objects.create(
            training=schedule.training,
            schedule=schedule,
            file=f'feedback_excel/{filename}',
            original_name=file.name,
            extracted_english_columns=english_columns,
            category=category
        )
        # --- FIX: Calculate and update faculty feedback score for this schedule BEFORE returning ---
        if category == 'feedback':
            try:
                import pandas as pd
                df = pd.read_excel(fs.path(filename))
                # Detect Pers No. column
                pers_no_col = None
                for col in df.columns:
                    if 'pers no' in col.lower():
                        pers_no_col = col
                        break
                # Detect F1Que-F4Que columns
                f1_col = next((c for c in df.columns if str(c).strip().startswith('F1Que')), None)
                f2_col = next((c for c in df.columns if str(c).strip().startswith('F2Que')), None)
                f3_col = next((c for c in df.columns if str(c).strip().startswith('F3Que')), None)
                f4_col = next((c for c in df.columns if str(c).strip().startswith('F4Que')), None)
                if pers_no_col and f1_col and f2_col and f3_col and f4_col:
                    feedback_list = []
                    weighted_scores = []
                    f1s, f2s, f3s, f4s = [], [], [], []
                    for _, row in df.iterrows():
                        try:
                            f1 = float(row[f1_col]) if pd.notnull(row[f1_col]) else None
                            f2 = float(row[f2_col]) if pd.notnull(row[f2_col]) else None
                            f3 = float(row[f3_col]) if pd.notnull(row[f3_col]) else None
                            f4 = float(row[f4_col]) if pd.notnull(row[f4_col]) else None
                            if f1 is not None: f1s.append(f1)
                            if f2 is not None: f2s.append(f2)
                            if f3 is not None: f3s.append(f3)
                            if f4 is not None: f4s.append(f4)
                            if None not in (f1, f2, f3, f4):
                                weighted = (f1 * 0.30) + (f2 * 0.25) + (f3 * 0.25) + (f4 * 0.20)
                                weighted_scores.append(weighted)
                            feedback_list.append({'F1': f1, 'F2': f2, 'F3': f3, 'F4': f4})
                        except Exception:
                            feedback_list.append({'F1': None, 'F2': None, 'F3': None, 'F4': None})
                    schedule.update_faculty_feedback_score(feedback_list)
                    avgF1 = round(sum(f1s)/len(f1s), 2) if f1s else None
                    avgF2 = round(sum(f2s)/len(f2s), 2) if f2s else None
                    avgF3 = round(sum(f3s)/len(f3s), 2) if f3s else None
                    avgF4 = round(sum(f4s)/len(f4s), 2) if f4s else None
                    rating = round(sum(weighted_scores)/len(weighted_scores), 2) if weighted_scores else None
            except Exception as e:
                import traceback
                print('Error updating faculty feedback score:', e)
                traceback.print_exc()
        # --- END FIX ---
        return JsonResponse({
            'success': True,
            'message': 'Excel file uploaded successfully',
            'filename': filename,
            'schedule_id': schedule_id
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@require_http_methods(["GET", "POST", "DELETE"])
def api_schedule_upload_document(request, schedule_id):
    """API for uploading, listing, and deleting schedule documents"""
    try:
        schedule = Schedule.objects.get(id=schedule_id)
    except Schedule.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Schedule not found'}, status=404)

    if request.method == 'POST':
        files = request.FILES.getlist('document')
        if not files:
            file = request.FILES.get('document')
            if file:
                files = [file]
        if not files:
            return JsonResponse({'success': False, 'error': 'No files uploaded'}, status=400)
        uploaded_docs = []
        for file in files:
            if not file.name.lower().endswith('.pdf'):
                return JsonResponse({'success': False, 'error': 'Only PDF files are allowed'}, status=400)
            doc = ScheduleDocument.objects.create(schedule=schedule, document=file)
            uploaded_docs.append({'id': doc.id, 'url': doc.document.url, 'name': doc.document.name})
        # Return all documents for this schedule
        all_docs = ScheduleDocument.objects.filter(schedule=schedule)
        doc_list = [{'id': d.id, 'url': d.document.url, 'name': d.document.name} for d in all_docs]
        return JsonResponse({'success': True, 'documents': doc_list})

    elif request.method == 'DELETE':
        # Expect ?doc_id= in query params
        doc_id = request.GET.get('doc_id')
        if not doc_id:
            return JsonResponse({'success': False, 'error': 'No document id provided'}, status=400)
        try:
            doc = ScheduleDocument.objects.get(id=doc_id, schedule=schedule)
            doc.document.delete(save=False)
            doc.delete()
        except ScheduleDocument.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Document not found'}, status=404)
        # Return all documents for this schedule
        all_docs = ScheduleDocument.objects.filter(schedule=schedule)
        doc_list = [{'id': d.id, 'url': d.document.url, 'name': d.document.name} for d in all_docs]
        return JsonResponse({'success': True, 'documents': doc_list})

    else:  # GET
        all_docs = ScheduleDocument.objects.filter(schedule=schedule)
        doc_list = [{'id': d.id, 'url': d.document.url, 'name': d.document.name} for d in all_docs]
        return JsonResponse({'success': True, 'documents': doc_list})

@login_required
@csrf_exempt
def api_schedule_update_type(request, schedule_id):
    """API for updating schedule type"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)
    try:
        data = json.loads(request.body)
        program_type = data.get('program_type')
        if not program_type:
            return JsonResponse({'success': False, 'error': 'No program_type provided'}, status=400)
        schedule = Schedule.objects.get(id=schedule_id)
        schedule.program_type = program_type
        schedule.save()
        return JsonResponse({'success': True, 'schedule': {
            'id': schedule.id,
            'program_type': schedule.program_type,
        }})
    except Schedule.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Schedule not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@login_required
def api_schedule_detail(request, schedule_id):
    try:
        schedule = Schedule.objects.select_related('program', 'faculty', 'hall', 'training').get(id=schedule_id)
    except Schedule.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Schedule not found'}, status=404)

    if request.method == 'GET':
        # Get faculty details for response
        faculty_data = []
        if schedule.training:
            for faculty_member in schedule.training.faculty.all():
                faculty_data.append({
                    'id': faculty_member.id,
                    'name': faculty_member.name,
                    'department': faculty_member.faculty_dept,
                    't_no': faculty_member.faculty_t_no
                })

        return JsonResponse({
            'success': True,
            'schedule': {
                'id': schedule.id,
                'program': schedule.program.name if schedule.program else '',
                'program_id': schedule.program.id if schedule.program else None,
                'program_type': schedule.program.program_type if schedule.program else 'Calendar Program',
                'training_id': schedule.training.id if schedule.training else None,
                'training_name': schedule.training.training_name if schedule.training else '',
                'faculty': schedule.faculty.name if schedule.faculty else '',
                'faculty_id': schedule.faculty.id if schedule.faculty else None,
                'alt_faculty': schedule.alt_faculty.name if schedule.alt_faculty else '',
                'alt_faculty_id': schedule.alt_faculty.id if schedule.alt_faculty else None,
                'hall': schedule.hall.name if schedule.hall else '',
                'hall_id': schedule.hall.id if schedule.hall else None,
                'date': schedule.date.strftime('%Y-%m-%d') if schedule.date else None,
                'end_date': schedule.end_date.strftime('%Y-%m-%d') if schedule.end_date else None,
                'start_time': schedule.start_time.strftime('%H:%M') if schedule.start_time else None,
                'end_time': schedule.end_time.strftime('%H:%M') if schedule.end_time else None,
                'duration': schedule.duration,
                'students': schedule.students,
                'equipment': schedule.equipment,
                'status': schedule.status,
                'notified_status': schedule.notified_status,
                'occupancy': f"{schedule.students}/{schedule.hall.capacity} ({int((schedule.students/schedule.hall.capacity)*100)}%)" if schedule.hall and schedule.hall.capacity and schedule.students else ''
            }
        })

    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            
            # Handle date fields with proper validation
            if 'date' in data:
                try:
                    date_str = data['date']
                    if date_str:
                        schedule.date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    else:
                        schedule.date = None
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)
            
            if 'end_date' in data:
                try:
                    end_date_str = data['end_date']
                    if end_date_str:
                        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                        if schedule.date and end_date < schedule.date:
                            return JsonResponse({'success': False, 'error': 'End date cannot be before start date'}, status=400)
                        schedule.end_date = end_date
                    else:
                        schedule.end_date = None
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Invalid end date format. Use YYYY-MM-DD.'}, status=400)

            # Handle time fields with proper validation
            if 'start_time' in data:
                try:
                    start_time_str = data['start_time']
                    if start_time_str:
                        schedule.start_time = datetime.strptime(start_time_str, '%H:%M').time()
                    else:
                        schedule.start_time = None
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Invalid start time format. Use HH:MM.'}, status=400)

            if 'end_time' in data:
                try:
                    end_time_str = data['end_time']
                    if end_time_str:
                        schedule.end_time = datetime.strptime(end_time_str, '%H:%M').time()
                    else:
                        schedule.end_time = None
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Invalid end time format. Use HH:MM.'}, status=400)

            # Add faculty_ids support with proper faculty assignment
            if 'faculty_ids' in data:
                faculty_ids = data.get('faculty_ids', [])
                if faculty_ids:
                    try:
                        # Get the first faculty member for the schedule
                        faculty = Faculty.objects.get(id=faculty_ids[0])
                        schedule.faculty = faculty
                        # Update the training's faculty with all selected faculty members
                        if schedule.training:
                            schedule.training.faculty.clear()  # Clear existing faculty assignments
                            for faculty_id in faculty_ids:
                                try:
                                    faculty_member = Faculty.objects.get(id=faculty_id)
                                    schedule.training.faculty.add(faculty_member)
                                except Faculty.DoesNotExist:
                                    continue
                    except Faculty.DoesNotExist:
                        schedule.faculty = None
                else:
                    schedule.faculty = None
                    if schedule.training:
                        schedule.training.faculty.clear()

            # Add hall_id support
            if 'hall_id' in data:
                hall_id = data.get('hall_id')
                if hall_id:
                    try:
                        schedule.hall = Hall.objects.get(id=hall_id)
                    except Hall.DoesNotExist:
                        return JsonResponse({'success': False, 'error': 'Invalid hall ID'}, status=400)
                else:
                    schedule.hall = None

            # Add alt_faculty_id support
            if 'alt_faculty_id' in data:
                alt_faculty_id = data.get('alt_faculty_id')
                if alt_faculty_id:
                    try:
                        schedule.alt_faculty = Faculty.objects.get(id=alt_faculty_id)
                    except Faculty.DoesNotExist:
                        return JsonResponse({'success': False, 'error': 'Invalid alt faculty ID'}, status=400)
                else:
                    schedule.alt_faculty = None

            # Safely handle numeric fields
            if 'duration' in data:
                duration_val = data['duration']
                if duration_val is not None and str(duration_val).strip() != '':
                    try:
                        duration = int(duration_val)
                        if duration < 1 or duration > 8:
                            return JsonResponse({'success': False, 'error': 'Duration must be between 1 and 8 hours'}, status=400)
                        schedule.duration = duration
                    except ValueError:
                        return JsonResponse({'success': False, 'error': 'Duration must be a valid number'}, status=400)
                else:
                    schedule.duration = None

            if 'students' in data:
                students_val = data['students']
                if students_val is not None and str(students_val).strip() != '':
                    try:
                        students = int(students_val)
                        if students < 1:
                            return JsonResponse({'success': False, 'error': 'Number of students must be positive'}, status=400)
                        schedule.students = students
                    except ValueError:
                        return JsonResponse({'success': False, 'error': 'Number of students must be a valid number'}, status=400)
                else:
                    schedule.students = None

            # Handle other fields
            if 'equipment' in data:
                schedule.equipment = data['equipment']
            if 'status' in data:
                schedule.status = data['status']
            # In the api_schedule_detail view, add this to the PUT method
            if 'notified_status' in data:
                print(f"[DEBUG] Received notified_status: {data['notified_status']}")
                schedule.notified_status = data['notified_status']
                print(f"[DEBUG] Saved notified_status: {schedule.notified_status}")

            # Save the schedule
            schedule.save()
            print(f"[DEBUG] After save, notified_status: {schedule.notified_status}")

            # Get faculty details for response
            faculty_data = []
            if schedule.training:
                for faculty_member in schedule.training.faculty.all():
                    faculty_data.append({
                        'id': faculty_member.id,
                        'name': faculty_member.name,
                        'department': faculty_member.faculty_dept,
                        't_no': faculty_member.faculty_t_no
                    })

            # Return the updated schedule data
            response_data = {
                'success': True,
                'schedule': {
                    'id': schedule.id,
                    'program': schedule.program.name if schedule.program else '',
                    'program_id': schedule.program.id if schedule.program else None,
                    'program_type': schedule.program.program_type if schedule.program else 'Calendar Program',
                    'training_id': schedule.training.id if schedule.training else None,
                    'training_name': schedule.training.training_name if schedule.training else '',
                    'faculty': schedule.faculty.name if schedule.faculty else '',
                    'faculty_id': schedule.faculty.id if schedule.faculty else None,
                    'alt_faculty': schedule.alt_faculty.name if schedule.alt_faculty else '',
                    'alt_faculty_id': schedule.alt_faculty.id if schedule.alt_faculty else None,
                    'hall': schedule.hall.name if schedule.hall else '',
                    'hall_id': schedule.hall.id if schedule.hall else None,
                    'date': schedule.date.strftime('%Y-%m-%d') if schedule.date else None,
                    'end_date': schedule.end_date.strftime('%Y-%m-%d') if schedule.end_date else None,
                    'start_time': schedule.start_time.strftime('%H:%M') if schedule.start_time else None,
                    'end_time': schedule.end_time.strftime('%H:%M') if schedule.end_time else None,
                    'duration': schedule.duration,
                    'students': schedule.students,
                    'equipment': schedule.equipment,
                    'status': schedule.status,
                    'notified_status': schedule.notified_status,
                    'occupancy': f"{schedule.students}/{schedule.hall.capacity} ({int((schedule.students/schedule.hall.capacity)*100)}%)" if schedule.hall and schedule.hall.capacity and schedule.students else ''
                }
            }
            print(f"[DEBUG] Sending response: {response_data}")
            return JsonResponse(response_data)

        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            import traceback
            print(f"Error updating schedule: {str(e)}")
            print(traceback.format_exc())
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    elif request.method == 'DELETE':
        schedule.delete()
        return JsonResponse({'success': True})
    else:
        return JsonResponse({'error': 'Invalid method'}, status=405)

@admin_required
def backup_restore_view(request):
    """Backup restore view - only admin"""
    return render(request, 'dashboard/backup_restore.html')

@admin_required
def create_backup(request):
    """Create backup - only admin"""
    messages.success(request, 'Backup created successfully!')
    return redirect('dashboard:backup_restore')

@admin_required
def restore_backup(request):
    """Restore backup - only admin"""
    messages.success(request, 'Backup restored successfully!')
    return redirect('dashboard:backup_restore')

@admin_required
def delete_backup(request):
    """Delete backup - only admin"""
    messages.success(request, 'Backup deleted successfully!')
    return redirect('dashboard:backup_restore')

@edit_delete_required
@require_http_methods(["POST"])
def update_program_type(request, program_id):
    """Update program type - only admin and staff"""
    program = get_object_or_404(Program, id=program_id)
    if request.method == 'POST':
        program.program_type = request.POST.get('program_type', program.program_type)
        program.save()
        messages.success(request, 'Program type updated successfully!')
    return redirect('dashboard:program_details', program_id=program.id)

@upload_download_required
def api_program_upload_document(request, program_id):
    """API for uploading program document"""
    return JsonResponse({'status': 'success'})

@login_required
def api_program_list_documents(request, program_id):
    """API for listing program documents"""
    return JsonResponse({'documents': []})

@admin_required
def api_program_delete_document(request, program_id):
    """API for deleting program document"""
    return JsonResponse({'status': 'success'})

@upload_download_required
def upload_program_document(request, program_id):
    """Upload program document"""
    messages.success(request, 'Document uploaded successfully!')
    return redirect('dashboard:program_details', program_id=program_id)

# Assessment views (placeholder)
@login_required
def pre_assessment(request):
    """Pre assessment - accessible to all users"""
    context = {
        'is_beta': get_user_role(request.user) == 'beta',
    }
    return render(request, 'dashboard/assessment/pre_assessment.html', context)

@login_required
def post_assessment(request):
    """Post assessment - accessible to all users"""
    context = {
        'is_beta': get_user_role(request.user) == 'beta',
    }
    return render(request, 'dashboard/assessment/post_assessment.html', context)

@login_required
def manager_checklist(request):
    """Manager checklist - accessible to all users"""
    return render(request, 'dashboard/assessment/manager_checklist.html')

@login_required
def roi_dashboard(request):
    """ROI dashboard - accessible to all users"""
    return render(request, 'dashboard/assessment/roi_dashboard.html')

# Other missing views
@login_required
def feedback_analysis(request, schedule_id):
    print("=== FEEDBACK ANALYSIS FUNCTION CALLED ===")
    print('[DEBUG] feedback_analysis view called for schedule_id:', schedule_id)
    import re
    def extract_english(col):
        match = re.search(r'\(([^)]+)\)', col)
        return match.group(1).strip() if match else col
    try:
        schedule = get_object_or_404(Schedule, id=schedule_id)
        training = schedule.training
        excel_upload = FeedbackExcelUpload.objects.filter(
            training=training,
            schedule=schedule,
            category='feedback',
        ).order_by('-uploaded_at').first()
        if not excel_upload or not excel_upload.file:
            return render(request, 'dashboard/assessment/analysis_error.html', {
                'error_message': 'No Excel file found for analysis for this schedule.'
            })
        file_path = excel_upload.file.path
        import pandas as pd
        df = pd.read_excel(file_path)
        original_columns = list(df.columns)
        english_columns = excel_upload.extracted_english_columns if excel_upload.extracted_english_columns else [extract_english(col) for col in df.columns]
        data_rows = df.to_dict(orient='records') if not df.empty else []
        total_rows = int(len(df))
        total_columns = int(len(df.columns))
        column_info = []
        for col in df.columns:
            col_data = df[col].dropna()
            column_info.append({
                'name': str(col),
                'type': str(df[col].dtype),
                'non_null_count': int(len(col_data)),
                'null_count': int(df[col].isnull().sum()),
                'unique_values': int(df[col].nunique()) if df[col].dtype in ['object', 'string'] else None
            })
        data_quality = {
            'total_cells': int(total_rows * total_columns),
            'null_cells': int(df.isnull().sum().sum()),
            'completeness_rate': float(((total_rows * total_columns) - df.isnull().sum().sum()) / (total_rows * total_columns) * 100)
        }
        chart_data = {
            'column_types': {},
            'null_distribution': {},
            'top_values': {}
        }
        for col in df.columns:
            dtype = str(df[col].dtype)
            chart_data['column_types'][dtype] = int(chart_data['column_types'].get(dtype, 0)) + 1
        null_counts = df.isnull().sum()
        chart_data['null_distribution'] = {str(col): int(count) for col, count in null_counts.items()}
        for col in df.columns:
            if df[col].dtype in ['object', 'string']:
                top_vals = df[col].value_counts().head(5)
                chart_data['top_values'][str(col)] = {str(k): int(v) for k, v in top_vals.items()}
        custom_metrics = []
        # Use dynamic category detection
        column_categories = detect_column_categories(english_columns)
        # Create custom metrics based on detected categories
        if len(column_categories['satisfaction']) >= 2:
            try:
                actual_cols = []
                for eng_col in column_categories['satisfaction']:
                    for orig_col in df.columns:
                        if eng_col and eng_col.lower() in str(orig_col).lower():
                            actual_cols.append(orig_col)
                            break
                if len(actual_cols) >= 2:
                    df['Total Satisfaction'] = df[actual_cols].mean(axis=1)
                    custom_metrics.append({'label': 'Total Satisfaction (Mean)', 'value': 'Total Satisfaction'})
            except Exception as e:
                print(f"Error creating Total Satisfaction metric: {e}")
        if column_categories['attendance']:
            custom_metrics.append({'label': 'Attendance Rate', 'value': 'Attendance'})
        if column_categories['score']:
            custom_metrics.append({'label': 'Average Score', 'value': 'Score'})
        if column_categories['knowledge']:
            custom_metrics.append({'label': 'Knowledge Assessment', 'value': 'Knowledge'})
        if column_categories['skill']:
            custom_metrics.append({'label': 'Skill Assessment', 'value': 'Skill'})
        if column_categories['behavior']:
            custom_metrics.append({'label': 'Behavior Assessment', 'value': 'Behavior'})
        dropdown_options = [{'label': col, 'value': col} for col in english_columns]
        dropdown_options = custom_metrics + dropdown_options
        def clean_col(col):
            return str(col).replace('\xa0', ' ').replace('\u200c', '').strip()
        print("[DEBUG] repr of all columns:", [repr(c) for c in df.columns])
        print("[DEBUG] cleaned columns:", [clean_col(c) for c in df.columns])
        for c in df.columns:
            print(f"[DEBUG] Checking column: {repr(c)} | cleaned: {clean_col(c)}")
        # Calculate final weighted average score for feedback (robust column detection)
        f1_col = next((c for c in df.columns if clean_col(c).startswith('F1Que')), None)
        f2_col = next((c for c in df.columns if clean_col(c).startswith('F2Que')), None)
        f3_col = next((c for c in df.columns if clean_col(c).startswith('F3Que')), None)
        f4_col = next((c for c in df.columns if clean_col(c).startswith('F4Que')), None)
        # Fallback: try exact F1, F2, F3, F4 if F1Que... not found
        if not (f1_col and f2_col and f3_col and f4_col):
            f1_col = f1_col or next((c for c in df.columns if clean_col(c) == 'F1'), None)
            f2_col = f2_col or next((c for c in df.columns if clean_col(c) == 'F2'), None)
            f3_col = f3_col or next((c for c in df.columns if clean_col(c) == 'F3'), None)
            f4_col = f4_col or next((c for c in df.columns if clean_col(c) == 'F4'), None)
        print('[DEBUG] Feedback column detection:', f1_col, f2_col, f3_col, f4_col)
        final_weighted_average = None
        valid_row_count = 0
        if f1_col and f2_col and f3_col and f4_col:
            weighted_scores = []
            for _, row in df.iterrows():
                try:
                    f1 = float(row[f1_col]) if pd.notnull(row[f1_col]) else None
                    f2 = float(row[f2_col]) if pd.notnull(row[f2_col]) else None
                    f3 = float(row[f3_col]) if pd.notnull(row[f3_col]) else None
                    f4 = float(row[f4_col]) if pd.notnull(row[f4_col]) else None
                    if None not in (f1, f2, f3, f4):
                        weighted = (f1 * 0.30) + (f2 * 0.25) + (f3 * 0.25) + (f4 * 0.20)
                        weighted_scores.append(weighted)
                        valid_row_count += 1
                except Exception:
                    continue
            if weighted_scores:
                final_weighted_average = round(sum(weighted_scores) / len(weighted_scores), 2)
        print(f'[DEBUG] Valid rows for weighted average: {valid_row_count}, Final Weighted Average: {final_weighted_average}')
        context = {
            'schedule': schedule,
            'excel_info': {
                'original_name': excel_upload.original_name,
                'filename': excel_upload.file.name,
                'uploaded_at': excel_upload.uploaded_at,
            },
            'analysis_data': {
                'total_rows': total_rows,
                'total_columns': total_columns,
                'column_info': column_info,
                'data_quality': data_quality,
                'chart_data': chart_data
            },
            'original_columns': original_columns,
            'english_columns': english_columns,
            'dropdown_options': dropdown_options,
            'data_rows': data_rows,
            'final_weighted_average': final_weighted_average,
            'detected_feedback_columns': {
                'f1_col': f1_col,
                'f2_col': f2_col,
                'f3_col': f3_col,
                'f4_col': f4_col,
            },
        }
        if final_weighted_average is None:
            debug_info = (
                f"[DEBUG] All columns: {list(df.columns)}\n"
                f"[DEBUG] First 3 rows: {df.head(3).to_dict(orient='records')}\n"
                f"[DEBUG] Feedback column detection: {f1_col}, {f2_col}, {f3_col}, {f4_col}\n"
                f"[DEBUG] Valid rows for weighted average: {valid_row_count}"
            )
            raise Exception(debug_info)
        return render(request, 'dashboard/assessment/feedback_analysis.html', context)
    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Error analyzing Excel file: {str(e)}')
        return redirect('dashboard:feedback_form')

@login_required
def api_feedback_analysis_data(request, schedule_id):
    try:
        schedule = get_object_or_404(Schedule, id=schedule_id)
        excel_upload = FeedbackExcelUpload.objects.filter(
            training=schedule.training,
            schedule=schedule,
            category='feedback',
        ).order_by('-uploaded_at').first()
        if not excel_upload or not excel_upload.file:
            return JsonResponse({'success': False, 'error': 'No Excel file found'})
        file_path = excel_upload.file.path
        import pandas as pd
        df = pd.read_excel(file_path)
        # Prepare detailed analysis data
        analysis_data = {
            'column_analysis': [],
            'data_distribution': {},
            'correlation_data': {},
            'summary_stats': {}
        }
        # Column analysis
        for col in df.columns:
            col_data = df[col].dropna()
            analysis_data['column_analysis'].append({
                'column': str(col),
                'type': str(df[col].dtype),
                'count': len(col_data),
                'null_count': df[col].isnull().sum(),
                'unique_count': df[col].nunique(),
                'min': float(col_data.min()) if df[col].dtype in ['int64', 'float64'] else None,
                'max': float(col_data.max()) if df[col].dtype in ['int64', 'float64'] else None,
                'mean': float(col_data.mean()) if df[col].dtype in ['int64', 'float64'] else None,
                'std': float(col_data.std()) if df[col].dtype in ['int64', 'float64'] else None
            })
        # Data distribution for categorical columns
        for col in df.columns:
            if df[col].dtype in ['object', 'string']:
                value_counts = df[col].value_counts().head(10)
                analysis_data['data_distribution'][str(col)] = {
                    'labels': list(value_counts.index),
                    'values': list(value_counts.values)
                }
        # Correlation matrix for numerical columns
        numerical_cols = df.select_dtypes(include=['int64', 'float64']).columns
        if len(numerical_cols) > 1:
            corr_matrix = df[numerical_cols].corr()
            analysis_data['correlation_data'] = {
                'columns': list(corr_matrix.columns),
                'correlation_matrix': corr_matrix.values.tolist()
            }
        # Summary statistics
        analysis_data['summary_stats'] = {
            'total_rows': len(df),
            'total_columns': len(df.columns),
            'numerical_columns': len(numerical_cols),
            'categorical_columns': len(df.select_dtypes(include=['object', 'string']).columns),
            'total_missing_values': df.isnull().sum().sum(),
            'completeness_percentage': ((len(df) * len(df.columns)) - df.isnull().sum().sum()) / (len(df) * len(df.columns)) * 100
        }
        return JsonResponse({
            'success': True,
            'analysis_data': analysis_data
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_http_methods(["POST"])
def analyze_attendance(request, training_ids):
    """Analyze attendance - accessible to all users"""
    try:
        # Split the training_ids string and get the first training
        # Remove any potential URL encoding
        training_id = training_ids.split(',')[0].strip()
        try:
            training_id = int(training_id)
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid training ID format'})
            
        training = get_object_or_404(Training, id=training_id)
        file = request.FILES.get('file')
        
        if not file:
            return JsonResponse({'success': False, 'error': 'No file uploaded'})
            
        if not file.name.endswith(('.xlsx', '.xls')):
            return JsonResponse({'success': False, 'error': 'Please upload an Excel file'})
            
        # Read the Excel file
        df = pd.read_excel(file)
        
        # Normalize column names (remove extra spaces, convert to lowercase)
        df.columns = [str(col).strip().lower() for col in df.columns]
        
        # Define expected columns with their possible variations
        column_mappings = {
            'sr no': ['sr no', 'srno', 'sr. no', 'sr. no.'],
            'p no.': ['p no.', 'pno', 'p no', 'pers no', 'persno'],
            'name': ['name', 'employee name', 'emp name'],
            'grade': ['grade', 'emp grade'],
            'department': ['department', 'dept', 'department name'],
            'company/contractor': ['company/contractor', 'company /contractor', 'company/ contractor', 'company / contractor', 'company', 'contractor'],
            'mobile no': ['mobile no', 'mobile no.', 'mobile', 'phone', 'contact no']
        }
        
        # Check for required columns using flexible matching
        missing_columns = []
        found_columns = {}
        
        for expected_col, variations in column_mappings.items():
            found = False
            for col in df.columns:
                if any(var in col for var in variations):
                    found_columns[expected_col] = col
                    found = True
                    break
            if not found:
                missing_columns.append(expected_col)
        
        if missing_columns:
            return JsonResponse({
                'success': False, 
                'error': f'Could not find columns: {", ".join(missing_columns)}. Available columns are: {", ".join(df.columns)}'
            })
        
        # Use the found column name for P No.
        p_no_col = found_columns['p no.']
        
        # Count rows with and without P No.
        p_no_count = int(df[p_no_col].notna().sum())
        without_p_no_count = int(df[p_no_col].isna().sum())
        total_count = int(len(df))
        
        # Update the most recent schedule's students count
        schedule = Schedule.objects.filter(training=training).order_by('-date', '-created_at').first()
        if schedule:
            schedule.students = p_no_count
            schedule.save()
        
        # Return only serializable data
        return JsonResponse({
            'success': True,
            'p_no_count': p_no_count,
            'without_p_no_count': without_p_no_count,
            'total_count': total_count,
            'message': f'Found {p_no_count} entries with P No. and {without_p_no_count} entries without P No.',
            'columns_found': found_columns  # Include this for debugging
        })
        
    except Exception as e:
        import traceback
        print(f"Error in analyze_attendance: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@csrf_exempt
def api_training_upload_attendance(request, training_ids):
    """API for uploading training attendance - accessible to all users"""
    if request.method == 'POST':
        try:
            # Get the first training ID from the comma-separated list
            training_id = training_ids.split(',')[0].strip()
            try:
                training_id = int(training_id)
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Invalid training ID format'})
                
            training = get_object_or_404(Training, id=training_id)
            file = request.FILES.get('file') or request.FILES.get('attendance_file')
            date_str = request.POST.get('date') or request.GET.get('date')
            
            if not date_str:
                return JsonResponse({'success': False, 'error': 'Date is required for attendance upload'})
            
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except Exception:
                return JsonResponse({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD.'})
            
            if not file:
                return JsonResponse({'success': False, 'error': 'No file uploaded'})
            
            if not file.name.endswith(('.xlsx', '.xls')):
                return JsonResponse({'success': False, 'error': 'Invalid file format. Please upload an Excel file.'})
            
            # Delete any existing attendance files for this training and date
            existing_files = TrainingAttendanceFile.objects.filter(training=training, date=date)
            for existing_file in existing_files:
                if existing_file.file:
                    existing_file.file.delete(save=False)
                existing_file.delete()
            
            # Create new attendance file
            att_file = TrainingAttendanceFile.objects.create(training=training, file=file, date=date)
            
            return JsonResponse({
                'success': True,
                'file_id': att_file.id,
                'file_url': att_file.file.url,
                'file_name': att_file.file.name,
                'uploaded_at': att_file.uploaded_at.isoformat()
            })
            
        except Exception as e:
            print(f"Error in api_training_upload_attendance: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

@login_required
def api_training_view_attendance(request, training_id):
    """API for viewing training attendance"""
    return JsonResponse({'attendance': []})

@upload_download_required
def api_training_download_attendance(request, training_ids):
    """API for downloading training attendance - requires upload/download permission"""
    try:
        # Get the first training ID from the comma-separated list
        training_id = training_ids.split(',')[0].strip()
        try:
            training_id = int(training_id)
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid training ID format'})
            
        training = get_object_or_404(Training, id=training_id)
        date_str = request.GET.get('date')
        
        att_file = None
        if date_str:
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
                att_file = training.attendance_files.filter(date=date).order_by('-uploaded_at').first()
            except Exception:
                att_file = training.attendance_files.order_by('-uploaded_at').first()
        else:
            att_file = training.attendance_files.order_by('-uploaded_at').first()
        
        if not att_file or not att_file.file:
            return JsonResponse({'success': False, 'error': 'No attendance file found'}, status=404)
        
        # Build a user-friendly filename: ProgramName_TrainingName_YYYY-MM-DD.xlsx
        program_name = training.program.name.replace(' ', '_') if training.program else ''
        training_name = training.training_name.replace(' ', '_')
        date_part = att_file.date.strftime('%Y-%m-%d') if att_file.date else ''
        ext = att_file.file.name.split('.')[-1]
        
        # Construct filename with program name if available
        if program_name:
            download_name = f"{program_name}_{training_name}_{date_part}.{ext}" if date_part else f"{program_name}_{training_name}.{ext}"
        else:
            download_name = f"{training_name}_{date_part}.{ext}" if date_part else f"{training_name}.{ext}"
        
        # Force download of the file
        response = FileResponse(att_file.file.open('rb'), as_attachment=True, filename=download_name)
        return response
    
    except Exception as e:
        print(f"Error in api_training_download_attendance: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def api_attendance_report(request):
    """
    CSV export of attendance with optional filters:
    ?start=YYYY-MM-DD&end=YYYY-MM-DD&status=Planned|Completed|Cancelled&program_id=ID
    """
    start = request.GET.get('start')
    end = request.GET.get('end')
    status = request.GET.get('status')
    program_id = request.GET.get('program_id')

    qs = TrainingAttendance.objects.select_related('training', 'training__program')
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    if status:
        status_training_ids = Schedule.objects.filter(status__iexact=status).values_list('training_id', flat=True)
        qs = qs.filter(training_id__in=status_training_ids)
    if program_id:
        qs = qs.filter(training__program_id=program_id)
    qs = qs.distinct()

    resp = HttpResponse(content_type='text/csv')
    filename = f"attendance_{start or 'all'}_{end or 'all'}.csv"
    resp['Content-Disposition'] = f'attachment; filename={filename}'
    writer = csv.writer(resp)
    writer.writerow(['Program', 'Training', 'P No', 'Employee Name', 'Date', 'Attended'])
    for att in qs:
        prog = att.training.program.name if att.training and att.training.program else ''
        writer.writerow([
            prog,
            att.training.training_name if att.training else '',
            att.employee.pers_no if att.employee else '',
            att.employee.name if att.employee else '',
            att.date.isoformat() if att.date else '',
            'Yes' if att.attended else 'No'
        ])
    return resp

@admin_required
def api_training_delete_attendance(request, training_ids):
    """API for deleting training attendance - only admin"""
    if request.method == 'POST':
        try:
            # Get the first training ID from the comma-separated list
            training_id = training_ids.split(',')[0].strip()
            try:
                training_id = int(training_id)
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Invalid training ID format'})
                
            training = get_object_or_404(Training, id=training_id)
            date_str = request.POST.get('date') or request.GET.get('date')
            
            if not date_str:
                return JsonResponse({'success': False, 'error': 'Date is required for attendance delete'})
            
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except Exception:
                return JsonResponse({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD.'})
            
            att_file = TrainingAttendanceFile.objects.filter(training=training, date=date).order_by('-uploaded_at').first()
            if not att_file:
                return JsonResponse({'success': False, 'error': 'No attendance file to delete'})
            
            import os
            from django.core.files.storage import default_storage
            
            try:
                # Delete the database record
                att_file.delete()
                
                # Try to delete the physical file
                try:
                    if default_storage.exists(att_file.file.name):
                        default_storage.delete(att_file.file.name)
                except Exception as e:
                    print(f"Warning: Could not delete physical file: {str(e)}")
                
                return JsonResponse({'success': True})
                
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=500)
                
        except Exception as e:
            print(f"Error in api_training_delete_attendance: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

@login_required
def api_training_attendance_status(request, training_ids):
    """API for training attendance status - accessible to all users"""
    try:
        # Get the first training ID from the comma-separated list
        training_id = training_ids.split(',')[0].strip()
        try:
            training_id = int(training_id)
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid training ID format'})
            
        training = get_object_or_404(Training, id=training_id)
        date_str = request.GET.get('date')
        
        if not date_str:
            return JsonResponse({
                'success': True, 
                'has_file': False, 
                'file_info': None, 
                'p_no_count': 0, 
                'without_p_no_count': 0, 
                'total_count': 0
            })
        
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            return JsonResponse({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD.'})
        
        att_file = TrainingAttendanceFile.objects.filter(training=training, date=date).order_by('-uploaded_at').first()
        if not att_file:
            return JsonResponse({
                'success': True,
                'has_file': False,
                'file_info': None,
                'p_no_count': 0,
                'without_p_no_count': 0,
                'total_count': 0,
            })
        
        import pandas as pd
        import os
        from django.core.files.storage import default_storage
        
        p_no_count = 0
        without_p_no_count = 0
        total_count = 0
        
        # Check if file exists and is accessible
        if not att_file.file:
            print(f"[DEBUG] No file attached to attendance record: {att_file.id}")
            return JsonResponse({
                'success': True,
                'has_file': False,
                'file_info': None,
                'p_no_count': 0,
                'without_p_no_count': 0,
                'total_count': 0,
            })
        
        # Check if file exists in storage
        if not default_storage.exists(att_file.file.name):
            print(f"[DEBUG] File does not exist in storage: {att_file.file.name}")
            return JsonResponse({
                'success': True,
                'has_file': False,
                'file_info': None,
                'p_no_count': 0,
                'without_p_no_count': 0,
                'total_count': 0,
            })
        
        try:
            # Read the Excel file
            file_path = att_file.file.path
            print(f"[DEBUG] Reading file: {file_path}")
            
            if not os.path.exists(file_path):
                print(f"[DEBUG] File path does not exist: {file_path}")
                return JsonResponse({
                    'success': True,
                    'has_file': False,
                    'file_info': None,
                    'p_no_count': 0,
                    'without_p_no_count': 0,
                    'total_count': 0,
                })
            
            df = pd.read_excel(file_path)
            
            # Clean column names
            df.columns = df.columns.str.strip()
            
            # Count rows with P No. and without P No.
            p_no_columns = [col for col in df.columns if 'p no' in col.lower() or 'pers no' in col.lower()]
            
            if p_no_columns:
                p_no_col = p_no_columns[0]
                # Count non-empty P No.s
                p_no_count = df[p_no_col].notna().sum()
                # Count empty P No.s
                without_p_no_count = df[p_no_col].isna().sum()
                total_count = len(df)
            else:
                # If no P No. column found, count all rows
                total_count = len(df)
                p_no_count = 0
                without_p_no_count = total_count
                
        except Exception as e:
            print(f"[DEBUG] Error reading attendance file: {str(e)}")
            import traceback
            print(traceback.format_exc())
            # Return file info even if we can't read it
            return JsonResponse({
                'success': True,
                'has_file': True,
                'file_info': {
                    'name': os.path.basename(att_file.file.name) if att_file.file else 'Unknown',
                    'uploaded_at': att_file.uploaded_at.isoformat(),
                    'size': att_file.file.size if att_file.file else 0,
                    'error': 'Could not read file content'
                },
                'p_no_count': 0,
                'without_p_no_count': 0,
                'total_count': 0,
            })
        
        return JsonResponse({
            'success': True,
            'has_file': True,
            'file_info': {
                'name': os.path.basename(att_file.file.name),
                'uploaded_at': att_file.uploaded_at.isoformat(),
                'size': att_file.file.size if att_file.file else 0
            },
            'p_no_count': int(p_no_count),
            'without_p_no_count': int(without_p_no_count),
            'total_count': int(total_count),
        })
        
    except Exception as e:
        print(f"[DEBUG] Unexpected error in api_training_attendance_status: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return JsonResponse({
            'success': False, 
            'error': f'Server error: {str(e)}'
        }, status=500)

@login_required
def api_training_attendance_list(request, training_id):
    """API for training attendance list"""
    return JsonResponse({'attendance': []})

@login_required
def generate_attendance_report(request):
    try:
        program_id = request.GET.get('program_id')
        training_ids = request.GET.get('training_ids', '').split(',')
        
        if not program_id or not training_ids:
            return JsonResponse({'error': 'Missing program_id or training_ids'}, status=400)
            
        program = Program.objects.get(id=program_id)
        trainings = Training.objects.filter(id__in=training_ids)
        
        # Create a new Excel workbook
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        import pandas as pd
        from datetime import datetime
        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance Report"
        
        # Add headers
        headers = [
            'Sr. No.', 'P No.', 'Employee Name', 'Employee Grade', 'Employee Department',
            'Company/Contractor', 'Mobile No', 'Program Type', 'Training Name',
            'Start Date', 'End Date', 'Start Time', 'End Time', 'Faculty T No.', 'Faculty', 'Hall', 'Gender'
        ]
        ws.append(headers)
        
        # Style the header row
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
        
        row_num = 2
        
        # Process each training
        for training in trainings:
            # Get the schedule for this training
            schedule = Schedule.objects.filter(training=training).first()
            
            # Get faculty T No. if faculty exists
            faculty_t_no = ''
            if schedule and schedule.faculty:
                faculty_employee = Employee.objects.filter(name=schedule.faculty.name).first()
                if faculty_employee:
                    faculty_t_no = faculty_employee.pers_no
            
            # Get the attendance file for this training
            att_file = TrainingAttendanceFile.objects.filter(training=training).first()
            
            if att_file and att_file.file:
                # Read the uploaded Excel file
                df = pd.read_excel(att_file.file.path)
                
                # Clean column names by stripping spaces
                df.columns = df.columns.str.strip()
                
                # Process each row in the attendance file
                for index, row in df.iterrows():
                    # Get P No. from the row and convert from float to integer string
                    p_no = row.get('P No.', '') or row.get('P No', '') or row.get('PNo', '')
                    if p_no and not pd.isna(p_no):  # Check if p_no is not NaN
                        p_no = str(int(float(p_no)))  # Convert float to int to string
                    else:
                        p_no = ''
                    
                    # Try to find employee by P No. matching pers_no
                    employee = None
                    if p_no:
                        employee = Employee.objects.filter(pers_no=p_no).first()
                    
                    # Get employee name, handling different possible column names
                    employee_name = row.get('Name', '') or row.get('name', '') or row.get('NAME', '')
                    
                    ws.append([
                        row_num - 1,  # Sr. No.
                        p_no,  # P No.
                        employee_name,  # Employee Name
                        row.get('Grade', '') or row.get('grade', '') or row.get('GRADE', ''),  # Employee Grade
                        row.get('Department', '') or row.get('department', '') or row.get('DEPARTMENT', ''),  # Employee Department
                        row.get('Company /Contractor', '') or row.get('Company/Contractor', '') or row.get('Company', ''),  # Company/Contractor
                        row.get('Mobile No', '') or row.get('Mobile No.', '') or row.get('Mobile', ''),  # Mobile No
                        program.program_type,  # Program Type
                        training.training_name,  # Training Name
                        schedule.date if schedule else '',  # Start Date
                        schedule.end_date if schedule else '',  # End Date
                        schedule.start_time if schedule else '',  # Start Time
                        schedule.end_time if schedule else '',  # End Time
                        faculty_t_no,  # Faculty T No.
                        schedule.faculty.name if schedule and schedule.faculty else '',  # Faculty
                        schedule.hall.name if schedule and schedule.hall else '',  # Hall
                        employee.gender_key if employee else ''  # Gender from Employee model
                    ])
                    row_num += 1
        
        # Save and return the Excel file
        from django.http import HttpResponse
        start_date = schedule.date if schedule else datetime.now()
        filename = f'{program.name}_{training.training_name}_{start_date.strftime("%d_%m_%Y")}.xlsx'
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@edit_delete_required
@require_http_methods(["POST"])
def update_training_type(request, training_id):
    """Update training type - only admin and staff"""
    training = get_object_or_404(Training, id=training_id)
    if request.method == 'POST':
        training.program_type = request.POST.get('program_type', training.program_type)
        training.save()
        messages.success(request, 'Training type updated successfully!')
    return redirect('dashboard:training_details', training_id=training.id)

@login_required
def get_training_schedule(request, training_id):
    """Get training schedule - accessible to all users"""
    try:
        # Get the training
        training = get_object_or_404(Training, id=training_id)
        
        # Get the date parameter
        date_str = request.GET.get('date')
        if not date_str:
            return JsonResponse({'error': 'Date parameter is required'}, status=400)
            
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
        
        # Get the schedule for this training and date
        schedule = Schedule.objects.filter(
            training=training,
            date=date
        ).select_related('faculty', 'hall', 'program').first()
        
        if not schedule:
            # Return a response indicating no schedule exists
            return JsonResponse({
                'success': True,
                'schedule_id': None,
                'message': 'No schedule found for this training and date'
            })
            
        # Format the schedule data
        schedule_data = {
            'success': True,
            'schedule_id': schedule.id,
            'program_id': training.program.id if training.program else None,
            'program': training.program.name if training.program else None,
            'program_type': training.program_type,
            'training_id': training.id,
            'training_name': training.training_name,
            'date': schedule.date.strftime('%Y-%m-%d'),
            'start_time': schedule.start_time.strftime('%H:%M') if schedule.start_time else None,
            'end_time': schedule.end_time.strftime('%H:%M') if schedule.end_time else None,
            'duration': schedule.duration,
            'faculty': schedule.faculty.name if schedule.faculty else None,
            'faculty_id': schedule.faculty.id if schedule.faculty else None,
            'faculty_dept': schedule.faculty.faculty_dept if schedule.faculty else None,
            'hall': schedule.hall.name if schedule.hall else None,
            'hall_id': schedule.hall.id if schedule.hall else None,
            'capacity': schedule.hall.capacity if schedule.hall else None,
            'students': schedule.students,
            'status': schedule.status,
            'document_url': schedule.document.url if schedule.document else None
        }
        
        return JsonResponse(schedule_data)
        
    except Exception as e:
        print(f"[DEBUG] Error in get_training_schedule: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@csrf_exempt
def api_update_training_type(request, training_id):
    """API for updating training type"""
    return JsonResponse({'status': 'success'})

@csrf_exempt
@role_required(['admin', 'alpha'])
def api_schedule_delete_excel(request, schedule_id):
    """Delete all uploaded Excel files and records for a schedule and a specific category (pre, post, or feedback) only."""
    from django.conf import settings
    import os
    from django.http import JsonResponse
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    try:
        category = request.POST.get('category') or request.GET.get('category')
        valid_categories = ['feedback', 'pre', 'post']
        if not category or category not in valid_categories:
            return JsonResponse({'success': False, 'error': f"Invalid or missing category. Must be one of: {', '.join(valid_categories)}"}, status=400)
        # Only delete FeedbackExcelUpload records for this schedule and the specified category
        uploads = FeedbackExcelUpload.objects.filter(schedule_id=schedule_id, category=category)
        deleted_files = []
        for upload in uploads:
            # Delete the file from disk
            if upload.file and upload.file.name:
                file_path = os.path.join(settings.MEDIA_ROOT, upload.file.name)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    deleted_files.append(upload.file.name)
            # Delete the record
            upload.delete()
        # Optionally, clear session info if present and matches this category
        session_key = f'feedback_excel_{schedule_id}'
        if session_key in request.session:
            del request.session[session_key]
        return JsonResponse({'success': True, 'deleted_files': deleted_files})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def pre_post_improvement_analysis(request, schedule_id):
    """Pre-post improvement analysis - accessible to all users"""
    return render(request, 'dashboard/pre_post_improvement_analysis.html')

@login_required
def schedule_program_view(request, program_id):
    """Schedule program view - accessible to all users"""
    return render(request, 'dashboard/schedule_program.html')

@login_required
def api_detailed_schedule(request):
    """API for detailed schedule"""
    return JsonResponse({'schedules': []})

@login_required
def api_detailed_schedule_detail(request, pk):
    """API for detailed schedule detail"""
    return JsonResponse({'schedule': {}})

# ============================================================================
# ERROR HANDLING
# ============================================================================

def handler403(request, exception=None):
    """Custom 403 error handler"""
    context = {
        'error_message': 'You do not have permission to access this page.',
        'user_role': get_user_role(request.user) if request.user.is_authenticated else None,
    }
    return render(request, 'dashboard/403.html', context, status=403)

def handler404(request, exception=None):
    """Custom 404 error handler"""
    context = {
        'error_message': 'The page you are looking for does not exist.',
        'user_role': get_user_role(request.user) if request.user.is_authenticated else None,
    }
    return render(request, 'dashboard/404.html', context, status=404)

def handler500(request):
    """Custom 500 error handler"""
    context = {
        'error_message': 'An internal server error occurred.',
        'user_role': get_user_role(request.user) if request.user.is_authenticated else None,
    }
    return render(request, 'dashboard/500.html', context, status=500)

@login_required
@csrf_exempt
def api_faculty_trainings(request, faculty_id):
    """API endpoint to get all trainings (schedules) for a given faculty, including per-question averages for F1-F4."""
    from .assessment_models import FeedbackExcelUpload
    from django.db.models import Q
    import pandas as pd
    from .models import Schedule
    # Get all schedules where this faculty is either the main or alt (and alt takes priority)
    schedules = Schedule.objects.filter(
        Q(alt_faculty_id=faculty_id) |
        (Q(faculty_id=faculty_id) & Q(alt_faculty__isnull=True))
    ).select_related('program', 'training', 'faculty', 'alt_faculty').order_by('-date')
    data = []
    for sched in schedules:
        # Determine the actual faculty for this schedule
        actual_faculty = sched.get_actual_faculty() if hasattr(sched, 'get_actual_faculty') else (sched.alt_faculty if sched.alt_faculty else sched.faculty)
        actual_faculty_name = actual_faculty.name if actual_faculty else ''
        actual_faculty_id = actual_faculty.id if actual_faculty else None
        actual_faculty_t_no = actual_faculty.faculty_t_no if actual_faculty else ''
        # Try to get the latest feedback Excel for this schedule
        feedback_upload = FeedbackExcelUpload.objects.filter(schedule=sched, category='feedback').order_by('-uploaded_at').first()
        avgF1 = avgF2 = avgF3 = avgF4 = rating = None
        weighted_scores = []  # Fix: ensure this is always defined
        if feedback_upload and feedback_upload.file:
            try:
                df = pd.read_excel(feedback_upload.file.path)
                f1_col = next((c for c in df.columns if str(c).strip().startswith('F1Que')), None)
                f2_col = next((c for c in df.columns if str(c).strip().startswith('F2Que')), None)
                f3_col = next((c for c in df.columns if str(c).strip().startswith('F3Que')), None)
                f4_col = next((c for c in df.columns if str(c).strip().startswith('F4Que')), None)
                if f1_col and f2_col and f3_col and f4_col:
                    f1s = df[f1_col].dropna().astype(float).tolist()
                    f2s = df[f2_col].dropna().astype(float).tolist()
                    f3s = df[f3_col].dropna().astype(float).tolist()
                    f4s = df[f4_col].dropna().astype(float).tolist()
                    for i in range(len(df)):
                        try:
                            f1 = float(df.iloc[i][f1_col]) if pd.notnull(df.iloc[i][f1_col]) else None
                            f2 = float(df.iloc[i][f2_col]) if pd.notnull(df.iloc[i][f2_col]) else None
                            f3 = float(df.iloc[i][f3_col]) if pd.notnull(df.iloc[i][f3_col]) else None
                            f4 = float(df.iloc[i][f4_col]) if pd.notnull(df.iloc[i][f4_col]) else None
                            if None not in (f1, f2, f3, f4):
                                weighted = (f1 * 0.30) + (f2 * 0.25) + (f3 * 0.25) + (f4 * 0.20)
                                weighted_scores.append(weighted)
                        except Exception:
                            continue
                    avgF1 = round(sum(f1s)/len(f1s), 2) if f1s else None
                    avgF2 = round(sum(f2s)/len(f2s), 2) if f2s else None
                    avgF3 = round(sum(f3s)/len(f3s), 2) if f3s else None
                    avgF4 = round(sum(f4s)/len(f4s), 2) if f4s else None
                    rating = round(sum(weighted_scores)/len(weighted_scores), 2) if weighted_scores else None
            except Exception as e:
                avgF1 = avgF2 = avgF3 = avgF4 = rating = None
        data.append({
            'program': sched.program.name if sched.program else '',
            'training': sched.training.training_name if sched.training else '',
            'date': sched.date.strftime('%Y-%m-%d') if sched.date else '',
            'status': sched.status,
            'rating': rating,
            'avgF1': avgF1,
            'avgF2': avgF2,
            'avgF3': avgF3,
            'avgF4': avgF4,
            'actual_faculty': actual_faculty_name,
            'actual_faculty_id': actual_faculty_id,
            'actual_faculty_t_no': actual_faculty_t_no,
        })
    return JsonResponse(data, safe=False)

@csrf_exempt
@require_POST
def api_scheduled_trainings_for_trainings(request):
    import json
    try:
        data = json.loads(request.body)
        training_ids = data.get('training_ids', [])
        if not training_ids:
            return JsonResponse({'error': 'No training_ids provided'}, status=400)
        schedules = Schedule.objects.filter(training_id__in=training_ids).select_related('training', 'faculty')
        result = []
        for s in schedules:
            result.append({
                'training_name': s.training.training_name if s.training else '',
                'faculty_name': s.faculty.name if s.faculty else '',
                'faculty_t_no': s.faculty.faculty_t_no if s.faculty else '',
                'rating': s.faculty_feedback_score if s.faculty_feedback_score is not None else '',
                'date': s.date.isoformat() if s.date else '',
            })
        return JsonResponse({'scheduled_trainings': result})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_GET
def employee_lookup(request):
    p_no = request.GET.get('p_no', '').strip()
    if not p_no:
        return JsonResponse({'success': False, 'error': 'No P No. provided'})
    emp = Employee.objects.filter(pers_no=p_no).first()
    if not emp:
        return JsonResponse({'success': False})
    # Attendance records
    attendance = []
    from .models import TrainingAttendance
    for att in TrainingAttendance.objects.filter(employee=emp).select_related('training__program'):
        attendance.append({
            'training_name': att.training.training_name if att.training else '-',
            'program_name': att.training.program.name if att.training and att.training.program else '-',
            'date': att.date.isoformat() if att.date else '-',
            'attended': att.attended,
        })
    return JsonResponse({
        'success': True,
        'pers_no': emp.pers_no,
        'name': emp.name,
        'department': getattr(emp, 'cost_center', '') or getattr(emp, 'department', ''),
        'gender_key': emp.gender_key,
        'employment_status': emp.employment_status,
        'attendance': attendance,
    })
