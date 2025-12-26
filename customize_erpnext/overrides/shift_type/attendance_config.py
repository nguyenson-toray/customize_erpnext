"""
Attendance Processing Configuration
Toggle between original and optimized processing versions
"""

import frappe


# ============================================================================
# FEATURE FLAGS
# ============================================================================

# Set to True to use optimized hybrid version
USE_OPTIMIZED_VERSION = True

# Performance thresholds
BULK_ATTENDANCE_ASYNC_THRESHOLD = 1000  # Records threshold for async processing
EMPLOYEE_CHUNK_SIZE = 100 if USE_OPTIMIZED_VERSION else 20
BULK_INSERT_BATCH_SIZE = 500
CHECKIN_UPDATE_BATCH_SIZE = 200


# ============================================================================
# VERSION SELECTOR
# ============================================================================

def get_bulk_update_method():
	"""
	Get the appropriate bulk update method based on configuration.

	Returns:
		str: Module path to the bulk_update_attendance method
	"""
	if USE_OPTIMIZED_VERSION:
		return "customize_erpnext.overrides.shift_type.shift_type_optimized.bulk_update_attendance_optimized"
	else:
		return "customize_erpnext.overrides.shift_type.shift_type.bulk_update_attendance"


def get_config():
	"""
	Get current attendance processing configuration.

	Returns:
		dict: Configuration settings
	"""
	return {
		"use_optimized": USE_OPTIMIZED_VERSION,
		"async_threshold": BULK_ATTENDANCE_ASYNC_THRESHOLD,
		"employee_chunk_size": EMPLOYEE_CHUNK_SIZE,
		"bulk_insert_batch_size": BULK_INSERT_BATCH_SIZE,
		"checkin_update_batch_size": CHECKIN_UPDATE_BATCH_SIZE,
		"bulk_update_method": get_bulk_update_method()
	}


@frappe.whitelist()
def get_attendance_config():
	"""API endpoint to get configuration from frontend."""
	return get_config()


@frappe.whitelist()
def set_optimized_mode(enabled=True):
	"""
	Enable or disable optimized processing mode.

	Args:
		enabled: True to use optimized version, False for original
	"""
	global USE_OPTIMIZED_VERSION
	USE_OPTIMIZED_VERSION = bool(enabled)

	frappe.msgprint(
		f"Attendance processing mode: {'OPTIMIZED' if enabled else 'ORIGINAL'}",
		indicator='green' if enabled else 'blue'
	)

	return get_config()


# ============================================================================
# PERFORMANCE MONITORING
# ============================================================================

class PerformanceMonitor:
	"""Context manager for monitoring performance."""

	def __init__(self, operation_name):
		self.operation_name = operation_name
		self.start_time = None
		self.end_time = None

	def __enter__(self):
		import time
		self.start_time = time.time()
		print(f"\n{'='*80}")
		print(f"🚀 Starting: {self.operation_name}")
		print(f"{'='*80}")
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		import time
		self.end_time = time.time()
		elapsed = self.end_time - self.start_time

		print(f"\n{'='*80}")
		print(f"✅ Completed: {self.operation_name}")
		print(f"⏱️  Time: {elapsed:.2f}s")
		print(f"{'='*80}\n")

		# Log to system
		frappe.logger().info(f"{self.operation_name} completed in {elapsed:.2f}s")

		return False  # Don't suppress exceptions


def log_performance_metrics(stats: dict, operation: str = "Attendance Processing"):
	"""
	Log detailed performance metrics.

	Args:
		stats: Statistics dictionary from processing
		operation: Operation name for logging
	"""
	frappe.logger().info(f"\n{'='*80}")
	frappe.logger().info(f"📊 PERFORMANCE METRICS: {operation}")
	frappe.logger().info(f"{'='*80}")
	frappe.logger().info(f"Version: {'OPTIMIZED' if USE_OPTIMIZED_VERSION else 'ORIGINAL'}")
	frappe.logger().info(f"Records Created/Updated: {stats.get('actual_records', 0)}")
	frappe.logger().info(f"Total Records in DB: {stats.get('total_records_in_db', 0)}")
	frappe.logger().info(f"Employees Processed: {stats.get('total_employees', 0)}")
	frappe.logger().info(f"Employees with Attendance: {stats.get('employees_with_attendance', 0)}")
	frappe.logger().info(f"Employees Skipped: {stats.get('employees_skipped', 0)}")
	frappe.logger().info(f"Days: {stats.get('total_days', 0)}")
	frappe.logger().info(f"Processing Time: {stats.get('processing_time', 0)}s")
	frappe.logger().info(f"Throughput: {stats.get('records_per_second', 0):.0f} records/sec")
	frappe.logger().info(f"Errors: {stats.get('errors', 0)}")
	frappe.logger().info(f"{'='*80}\n")


# ============================================================================
# A/B TESTING SUPPORT
# ============================================================================

@frappe.whitelist()
def benchmark_both_versions(from_date, to_date, employees=None, sample_size=None):
	"""
	Run both original and optimized versions for comparison.

	WARNING: This will process data twice. Only use for testing!

	Args:
		from_date: Start date
		to_date: End date
		employees: Optional employee list
		sample_size: Optional limit for testing (e.g., 10 employees)

	Returns:
		dict: Comparison results
	"""
	import time
	import json

	if employees and isinstance(employees, str):
		employees = json.loads(employees)

	# Limit to sample size if provided
	if sample_size and employees:
		employees = employees[:int(sample_size)]

	results = {
		"from_date": from_date,
		"to_date": to_date,
		"employee_count": len(employees) if employees else "all"
	}

	# Test original version
	print("\n" + "="*80)
	print("🧪 TESTING ORIGINAL VERSION")
	print("="*80)

	try:
		from customize_erpnext.overrides.shift_type.shift_type import bulk_update_attendance

		start = time.time()
		original_result = bulk_update_attendance(
			from_date=from_date,
			to_date=to_date,
			employees=json.dumps(employees) if employees else None,
			force_sync=1  # Force synchronous for testing
		)
		original_time = time.time() - start

		results["original"] = {
			"time": original_time,
			"records": original_result.get("result", {}).get("actual_records", 0),
			"throughput": original_result.get("result", {}).get("records_per_second", 0)
		}

		print(f"✅ Original: {original_time:.2f}s, {results['original']['records']} records")

	except Exception as e:
		results["original"] = {"error": str(e)}
		print(f"❌ Original failed: {str(e)}")

	# Test optimized version
	print("\n" + "="*80)
	print("🧪 TESTING OPTIMIZED VERSION")
	print("="*80)

	try:
		from customize_erpnext.overrides.shift_type.shift_type_optimized import bulk_update_attendance_optimized

		start = time.time()
		optimized_result = bulk_update_attendance_optimized(
			from_date=from_date,
			to_date=to_date,
			employees=json.dumps(employees) if employees else None,
			force_sync=1
		)
		optimized_time = time.time() - start

		results["optimized"] = {
			"time": optimized_time,
			"records": optimized_result.get("result", {}).get("actual_records", 0),
			"throughput": optimized_result.get("result", {}).get("records_per_second", 0)
		}

		print(f"✅ Optimized: {optimized_time:.2f}s, {results['optimized']['records']} records")

	except Exception as e:
		results["optimized"] = {"error": str(e)}
		print(f"❌ Optimized failed: {str(e)}")

	# Calculate improvement
	if "error" not in results.get("original", {}) and "error" not in results.get("optimized", {}):
		improvement = ((results["original"]["time"] - results["optimized"]["time"]) / results["original"]["time"]) * 100
		speedup = results["original"]["time"] / results["optimized"]["time"]

		results["comparison"] = {
			"improvement_percent": round(improvement, 1),
			"speedup_factor": round(speedup, 2),
			"time_saved": round(results["original"]["time"] - results["optimized"]["time"], 2)
		}

		print("\n" + "="*80)
		print("📊 COMPARISON RESULTS")
		print("="*80)
		print(f"⚡ Speedup: {speedup:.2f}x faster")
		print(f"📈 Improvement: {improvement:.1f}%")
		print(f"⏱️  Time saved: {results['comparison']['time_saved']:.2f}s")
		print("="*80 + "\n")

	return results


print("✅ Attendance Configuration loaded")
