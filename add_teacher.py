#!/usr/bin/env python3
"""
Script to add teacher to MongoDB
"""
from src.repositories.mongo_repository import MongoRepository

def add_teacher():
    mongo_repo = MongoRepository()
    
    if mongo_repo.db is None:
        print("MongoDB not connected")
        return
    
    teacher_data = {
        "id": "bafceeb1-8638-4854-8210-7be787420123",
        "timestamp": "2025-02-19T11:52:08.604816",
        "name": "Obaid",
        "email": "obaid@codegnan.com",
        "password": "$2b$12$kE58Dz9cmjSzsBEIw45O1Ovsi7FZMuqkru27nZhXAL9//rJRqxYH.",
        "PhNumber": "+919701296465",
        "Designation": [
            "Python", "Flask", "Java", "Frontend", "Aptitude", 
            "MySQL", "SoftSkills", "DSA-Python", "DSA-Java"
        ],
        "location": "vijayawada",
        "usertype": "Mentor",
        "status": True,
        "telegram_id": None
    }
    
    # Insert teacher
    result = mongo_repo.db.teachers.insert_one(teacher_data)
    print(f"Teacher added with ID: {result.inserted_id}")
    print("Now try /start again in the bot")

if __name__ == "__main__":
    add_teacher()