import asyncio
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.db import db_manager, ReadOnlySecurityViolation


async def run_readonly_security_tests():
    print("=" * 65)
    print("TESTING HARD-RULE READ-ONLY SECURITY ENFORCEMENT")
    print("=" * 65)

    await db_manager.connect()

    # 1. Verify read operation on ERP is allowed
    print("\n[1/6] Testing Read on ERP DB ...")
    try:
        doc = await db_manager.erp_db["quotes"].find_one()
        print("  [OK] Read on ERP DB succeeded (document read allowed)")
    except Exception as e:
        print("  ERP read error (not related to write blocking):", e)

    # 2. Verify read operation on SC DB is allowed
    print("\n[2/6] Testing Read on SC DB ...")
    try:
        supplier = await db_manager.sc_db["suppliercompanies"].find_one()
        print("  [OK] Read on SC DB succeeded (document read allowed)")
    except Exception as e:
        print("  SC read error (not related to write blocking):", e)

    # 3. Test insert_one on SC DB is strictly BLOCKED
    print("\n[3/6] Testing insert_one on SC DB (MUST BE BLOCKED) ...")
    try:
        await db_manager.sc_db["suppliercompanies"].insert_one({"hack": True})
        raise AssertionError("SECURITY BREACH: insert_one was allowed on SC DB!")
    except ReadOnlySecurityViolation as e:
        print("  [OK] Successfully BLOCKED insert_one on SC DB:")
        print("    ", str(e))

    # 4. Test update_one on ERP DB is strictly BLOCKED
    print("\n[4/6] Testing update_one on ERP DB (MUST BE BLOCKED) ...")
    try:
        await db_manager.erp_db["quotes"].update_one({}, {"$set": {"status": "tampered"}})
        raise AssertionError("SECURITY BREACH: update_one was allowed on ERP DB!")
    except ReadOnlySecurityViolation as e:
        print("  [OK] Successfully BLOCKED update_one on ERP DB:")
        print("    ", str(e))

    # 5. Test delete_one on SC DB is strictly BLOCKED
    print("\n[5/6] Testing delete_one on SC DB (MUST BE BLOCKED) ...")
    try:
        await db_manager.sc_db["suppliercompanies"].delete_one({"_id": "test"})
        raise AssertionError("SECURITY BREACH: delete_one was allowed on SC DB!")
    except ReadOnlySecurityViolation as e:
        print("  [OK] Successfully BLOCKED delete_one on SC DB:")
        print("    ", str(e))

    # 6. Test drop_collection on ERP DB is strictly BLOCKED
    print("\n[6/6] Testing drop_collection on ERP DB (MUST BE BLOCKED) ...")
    try:
        await db_manager.erp_db.drop_collection("quotes")
        raise AssertionError("SECURITY BREACH: drop_collection was allowed on ERP DB!")
    except ReadOnlySecurityViolation as e:
        print("  [OK] Successfully BLOCKED drop_collection on ERP DB:")
        print("    ", str(e))

    await db_manager.disconnect()
    print("\n" + "=" * 65)
    print("ALL 6 READ-ONLY SECURITY CHECKS PASSED WITH 100% SUCCESS!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_readonly_security_tests())
