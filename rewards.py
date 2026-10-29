"""
rewards.py - Green Pulse Points, Threshold Logic & Simulated Rewards Engine
Manages points balances, transaction audit trails, 100-point reward threshold,
redemptions, and unique demonstration voucher code generation.
"""

import uuid
from datetime import datetime
from database import get_db_connection

REWARD_THRESHOLD = 100
ORG_REWARD_THRESHOLD = 1000  # Mandatory organizational reward threshold (1,000 pts)


def get_org_points_summary(org_id):
    """Wrapper referencing database.get_org_points_summary for organization threshold metrics."""
    import database
    return database.get_org_points_summary(org_id)


def get_org_rewards_catalog(org_id):
    """Wrapper referencing database.get_org_rewards_catalog."""
    import database
    return database.get_org_rewards_catalog(org_id)


def redeem_org_reward(org_id, user_id, reward_id):
    """Wrapper referencing database.redeem_org_reward."""
    import database
    return database.redeem_org_reward(org_id, user_id, reward_id)


def get_user_points_summary(user_id):
    """
    Computes current points balance, total earned, total spent,
    and threshold metrics (100-point milestone).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        COALESCE(SUM(CASE WHEN transaction_type = 'earned' THEN points ELSE 0 END), 0) AS total_earned,
        COALESCE(SUM(CASE WHEN transaction_type = 'redeemed' THEN points ELSE 0 END), 0) AS total_redeemed
    FROM points_transactions
    WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()

    total_earned = row["total_earned"]
    total_redeemed = row["total_redeemed"]
    balance = max(0, total_earned - total_redeemed)

    # 100 points threshold calculation
    points_needed = max(0, REWARD_THRESHOLD - balance)
    progress_percentage = min(100.0, round((balance / REWARD_THRESHOLD) * 100, 1))
    can_redeem = balance >= REWARD_THRESHOLD

    # Fetch transaction history
    cursor.execute("""
    SELECT id, transaction_type, points, description, reference_type, created_at
    FROM points_transactions
    WHERE user_id = ?
    ORDER BY created_at DESC, id DESC
    """, (user_id,))
    transactions = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        "balance": balance,
        "total_earned": total_earned,
        "total_redeemed": total_redeemed,
        "threshold": REWARD_THRESHOLD,
        "points_needed": points_needed,
        "progress_percentage": progress_percentage,
        "can_redeem": can_redeem,
        "transactions": transactions
    }


def get_rewards_catalog(user_id):
    """
    Returns available rewards grouped by target audience (Individual vs Organization)
    and marks eligibility based on the user's current points balance.
    """
    points_info = get_user_points_summary(user_id)
    balance = points_info["balance"]

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get user account type
    cursor.execute("SELECT account_type FROM users WHERE id = ?", (user_id,))
    u_row = cursor.fetchone()
    account_type = u_row["account_type"] if u_row else "individual"

    cursor.execute("SELECT * FROM rewards WHERE is_active = 1 ORDER BY points_cost ASC")
    all_rewards = []
    ind_rewards = []
    org_rewards = []

    for r in cursor.fetchall():
        item = dict(r)
        item["is_eligible"] = balance >= item["points_cost"]
        item["points_short"] = max(0, item["points_cost"] - balance)
        all_rewards.append(item)
        if item.get("target_audience") == "organization":
            org_rewards.append(item)
        else:
            ind_rewards.append(item)

    # Fetch user's redeemed vouchers
    cursor.execute("""
    SELECT rr.id, rr.voucher_code, rr.points_spent, rr.status, rr.redeemed_at,
           r.title as reward_title, r.category, r.terms, r.icon, r.target_audience
    FROM reward_redemptions rr
    JOIN rewards r ON rr.reward_id = r.id
    WHERE rr.user_id = ?
    ORDER BY rr.redeemed_at DESC
    """, (user_id,))
    redemptions = [dict(r) for r in cursor.fetchall()]

    conn.close()

    # Prioritize user's own domain rewards
    active_catalog = org_rewards if account_type == "organization" else ind_rewards

    return {
        "rewards": active_catalog,
        "all_rewards": all_rewards,
        "individual_rewards": ind_rewards,
        "organization_rewards": org_rewards,
        "account_type": account_type,
        "redemptions": redemptions,
        "balance": balance,
        "can_redeem": points_info["can_redeem"],
        "points_needed": points_info["points_needed"],
        "progress_percentage": points_info["progress_percentage"]
    }


def redeem_reward(user_id, reward_id):
    """
    Redeems a reward from the catalog.
    Validates balance, deducts points, generates unique demo voucher code,
    and prevents duplicate or overspending.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify reward exists
    cursor.execute("SELECT * FROM rewards WHERE id = ? AND is_active = 1", (reward_id,))
    reward = cursor.fetchone()
    if not reward:
        conn.close()
        return {"success": False, "message": "Reward not found or currently unavailable."}

    cost = reward["points_cost"]

    # Verify balance
    cursor.execute("""
    SELECT 
        COALESCE(SUM(CASE WHEN transaction_type = 'earned' THEN points ELSE 0 END), 0) -
        COALESCE(SUM(CASE WHEN transaction_type = 'redeemed' THEN points ELSE 0 END), 0) AS balance
    FROM points_transactions
    WHERE user_id = ?
    """, (user_id,))
    curr_balance = cursor.fetchone()["balance"]

    if curr_balance < cost:
        conn.close()
        return {
            "success": False, 
            "message": f"Insufficient points balance ({curr_balance} pts). You need {cost} pts to redeem this reward."
        }

    # Generate unique demonstration coupon code
    prefix = reward["voucher_prefix"]
    unique_suffix = uuid.uuid4().hex[:6].upper()
    voucher_code = f"{prefix}-{datetime.now().year}-{unique_suffix}"

    try:
        # Record redemption
        cursor.execute("""
        INSERT INTO reward_redemptions (user_id, reward_id, voucher_code, points_spent, status)
        VALUES (?, ?, ?, ?, 'active')
        """, (user_id, reward_id, voucher_code, cost))
        redemption_id = cursor.lastrowid

        # Record debit transaction
        cursor.execute("""
        INSERT INTO points_transactions (user_id, transaction_type, points, description, reference_id, reference_type)
        VALUES (?, 'redeemed', ?, ?, ?, 'reward_redemption')
        """, (user_id, cost, f"Redeemed: {reward['title']} (Voucher: {voucher_code})", redemption_id))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": f"Reward redeemed successfully! Your demonstration code is {voucher_code}.",
            "voucher_code": voucher_code,
            "points_spent": cost,
            "remaining_balance": curr_balance - cost
        }

    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "message": f"Error during redemption: {str(e)}"}


def approve_submission(submission_id, reviewer_id=2, reviewer_notes="Evidence verified by Green Pulse reviewer."):
    """
    Admin workflow: Reviews and approves evidence submission.
    Awards points to the user once and transitions status to 'approved'.
    Enforces strict duplicate award prevention.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT es.*, c.title as challenge_title, c.reward_points, c.id as ch_id
    FROM evidence_submissions es
    JOIN challenges c ON es.challenge_id = c.id
    WHERE es.id = ?
    """, (submission_id,))
    sub = cursor.fetchone()

    if not sub:
        conn.close()
        return {"success": False, "message": "Evidence submission record not found."}

    if sub["status"] == "approved" or sub["points_awarded"] > 0:
        conn.close()
        return {"success": False, "message": "Points have already been awarded for this submission. Duplicate awards are blocked."}

    user_id = sub["user_id"]
    points = sub["reward_points"]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Update submission status
        cursor.execute("""
        UPDATE evidence_submissions
        SET status = 'approved',
            reviewer_notes = ?,
            reviewed_at = ?,
            points_awarded = ?
        WHERE id = ?
        """, (reviewer_notes, now_str, points, submission_id))

        # Update user_challenges record
        cursor.execute("""
        UPDATE user_challenges
        SET status = 'completed',
            completed_at = ?
        WHERE user_id = ? AND challenge_id = ?
        """, (now_str, user_id, sub["challenge_id"]))

        # Add points transaction
        cursor.execute("""
        INSERT INTO points_transactions (user_id, transaction_type, points, description, reference_id, reference_type)
        VALUES (?, 'earned', ?, ?, ?, 'challenge_approval')
        """, (
            user_id, 
            points, 
            f"Approved: {sub['challenge_title']} (Review: {reviewer_notes})", 
            submission_id
        ))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": f"Submission approved! Awarded {points} Green Pulse points.",
            "points_awarded": points
        }
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "message": f"Approval error: {str(e)}"}


def reject_submission(submission_id, reviewer_id=2, reviewer_notes="Evidence unclear or does not match challenge guidelines."):
    """
    Admin workflow: Rejects evidence submission with a feedback note.
    Does not award points. Resets challenge status so user can rectify.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM evidence_submissions WHERE id = ?", (submission_id,))
    sub = cursor.fetchone()
    if not sub:
        conn.close()
        return {"success": False, "message": "Submission not found."}

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        cursor.execute("""
        UPDATE evidence_submissions
        SET status = 'rejected',
            reviewer_notes = ?,
            reviewed_at = ?,
            points_awarded = 0
        WHERE id = ?
        """, (reviewer_notes, now_str, submission_id))

        # Reset user_challenges status back to 'accepted' so the user can re-attempt
        cursor.execute("""
        UPDATE user_challenges
        SET status = 'accepted'
        WHERE user_id = ? AND challenge_id = ?
        """, (sub["user_id"], sub["challenge_id"]))

        conn.commit()
        conn.close()
        return {"success": True, "message": "Submission rejected with reviewer feedback."}
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "message": f"Rejection error: {str(e)}"}
