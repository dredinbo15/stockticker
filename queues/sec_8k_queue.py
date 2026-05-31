"""
SEC 8-K data queue wrapper.
"""

from queues.tasks import process_raw_sec_8k_report


class SEC8KQueue:
    def add_to_queue(self, report_data):
        """Add parsed SEC 8-K report to processing queue."""
        report_dict = {
            'issuer_cik': report_data.issuer_cik,
            'issuer_name': report_data.issuer_name,
            'filing_date': report_data.filing_date.isoformat(),
            'description': report_data.description,
            'content': report_data.content,
            'item_summary': report_data.item_summary,
            'form_url': report_data.form_url,
            'report_hash': report_data.report_hash,
        }
        process_raw_sec_8k_report.delay(report_dict)
