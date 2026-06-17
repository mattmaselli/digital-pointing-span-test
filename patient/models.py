from django.db import models
from doctor.models import Doctor

# Create your models here.

#TESTS
# 1 to N relationship with Doctor
class Test(models.Model):
    STATUS_CHOICES = [
        ("INCOMPLETE", "Incomplete"),
        ("COMPLETE", "Complete"),
        ("ENDED_EARLY", "Abandoned"),
        ("EXPIRED", "Expired"),
    ]

    #* USE test.id in wireframes for test id
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name = "tests")
    patient_age = models.PositiveIntegerField()

    # Completed, incomplete, abandoned, or expired
    status = models.CharField(max_length=20, choices = STATUS_CHOICES, default = "INCOMPLETE")
    
    # Scheduled date/time set by doctor
    scheduled_for = models.DateTimeField(null=True, blank=True)

    # Timestamp section 
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    #test link
    access_token = models.CharField(max_length=64, unique=True)
    def __str__(self):
        return f"Test {self.id} - {self.status}"
    

# TEST TRIALS/QUESTIONS
# 1 to N Relationship with Test
class Trial(models.Model):
    TRIAL_TYPE_OPTIONS =[
        ("DIGIT", "Digit"),
        ("ALPHANUMERIC", "Alphanumeric"),
    ]

    SPAN_OPTIONS = [
        (4, "4-span"),
        (5, "5-span"),
    ]

    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name = "trials")
    trial_type= models.CharField(max_length=20, choices = TRIAL_TYPE_OPTIONS)
    trial_number = models.PositiveIntegerField()
    span_length = models.PositiveIntegerField(choices = SPAN_OPTIONS)


    # unsure if displayed sequence will include spaces
    #, so 10 to be safe but this can be changed to 5.
    displayed_sequence = models.CharField(max_length=10) 

    # the timestamp that the sequence finishes at
    # important to record latency times
    # however, have to record each user keystroke to work
    # latency = first keystroke - sequence finished at
    # subsequent keystroke latencies dependent on previous keystroke
    sequence_finished_at = models.DateTimeField(null=True, blank = True)

    def __str__(self):
        return f"Test {self.test.id} - Trial {self.trial_number}"
    

# Response
# 1 to 1 relationship with Trial
class Response(models.Model):

    trial = models.OneToOneField("patient.Trial", on_delete=models.CASCADE, related_name = "response")

    # the enter sequence to be used to compare to displayed sequence
    user_sequence = models.CharField(max_length=50, blank=True, default="")

    is_exact_match = models.BooleanField(default=False)
    correct_positions = models.PositiveIntegerField(default = 0)
    accuracy = models.FloatField(default = 0.0) # percentage
    response_latency = models.FloatField(null=True, blank = True)

    def __str__(self):
        return f"Response for Trial {self.trial.trial_number}"
    
# KEYSTROKE
# 1 to N relatonship with Response, used for latencies
class Keystroke(models.Model):
    response = models.ForeignKey(
        "patient.Response", 
        on_delete=models.CASCADE,
        related_name = "keystrokes"
    )
    
    key_pressed = models.CharField(max_length = 1)
    position=models.PositiveIntegerField()

    # latencies to be recorded in seconds
    latency = models.FloatField(null=True,blank=True)
    

    def __str__(self):
        return f"{self.key_pressed} (position {self.position} ) for Trial {self.response.trial.trial_number}"




