"""Backend API Testing - Water Analytics Endpoint Verification"""
import requests
import json

# Backend URL from frontend/.env
BASE_URL = "https://650211ed-6be8-4922-a777-d5bd079fc6e2.preview.emergentagent.com/api"

# Test credentials
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "Test1234!"

def test_water_analytics():
    """Test water analytics endpoint after route ordering fix."""
    print("\n" + "="*80)
    print("WATER ANALYTICS ENDPOINT VERIFICATION TEST")
    print("="*80)
    
    # Step 1: Login
    print("\n[1/3] Logging in with test@example.com...")
    login_response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    
    if login_response.status_code != 200:
        print(f"❌ LOGIN FAILED: {login_response.status_code}")
        print(f"Response: {login_response.text}")
        return False
    
    login_data = login_response.json()
    access_token = login_data.get("access_token")
    print(f"✅ Login successful. Token: {access_token[:20]}...")
    
    # Step 2: Test GET /api/water/analytics?days=7
    print("\n[2/3] Testing GET /api/water/analytics?days=7...")
    headers = {"Authorization": f"Bearer {access_token}"}
    
    analytics_response = requests.get(
        f"{BASE_URL}/water/analytics?days=7",
        headers=headers
    )
    
    print(f"Status Code: {analytics_response.status_code}")
    
    if analytics_response.status_code != 200:
        print(f"❌ ANALYTICS REQUEST FAILED: {analytics_response.status_code}")
        print(f"Response: {analytics_response.text}")
        return False
    
    # Step 3: Verify response structure
    print("\n[3/3] Verifying response structure...")
    analytics_data = analytics_response.json()
    
    print(f"\nResponse JSON:")
    print(json.dumps(analytics_data, indent=2))
    
    # Check required fields
    required_fields = ["days", "goal_ml", "avg_daily_ml", "days_goal_met", "history"]
    missing_fields = []
    
    for field in required_fields:
        if field not in analytics_data:
            missing_fields.append(field)
    
    if missing_fields:
        print(f"\n❌ MISSING REQUIRED FIELDS: {missing_fields}")
        return False
    
    print(f"\n✅ All required fields present:")
    print(f"   - days: {analytics_data['days']}")
    print(f"   - goal_ml: {analytics_data['goal_ml']}")
    print(f"   - avg_daily_ml: {analytics_data['avg_daily_ml']}")
    print(f"   - days_goal_met: {analytics_data['days_goal_met']}")
    print(f"   - history: {len(analytics_data['history'])} entries")
    
    # Verify history structure
    if analytics_data['history']:
        print(f"\n✅ Sample history entry:")
        sample = analytics_data['history'][0]
        print(f"   {json.dumps(sample, indent=2)}")
    
    print("\n" + "="*80)
    print("✅ WATER ANALYTICS ENDPOINT TEST PASSED")
    print("="*80)
    return True

if __name__ == "__main__":
    try:
        success = test_water_analytics()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST FAILED WITH EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()
        exit(1)
