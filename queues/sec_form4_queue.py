"""
SEC Form 4 data queue wrapper.
"""

from queues.tasks import save_sec_form4

class SECForm4Queue:
    def add_to_queue(self, form4_data):
        """Add SEC Form 4 data to processing queue."""
        form4_dict = {
            'issuer_cik': form4_data.issuer_cik,
            'issuer_name': form4_data.issuer_name,
            'reporter_cik': form4_data.reporter_cik,
            'reporter_name': form4_data.reporter_name,
            'transaction_date': form4_data.transaction_date.isoformat(),
            'transaction_code': form4_data.transaction_code,
            'shares': form4_data.shares,
            'price': form4_data.price,
            'security_title': form4_data.security_title,
            'transaction_type': form4_data.transaction_type,
            'ownership_nature': form4_data.ownership_nature,
            'form_url': form4_data.form_url
        }
        save_sec_form4.delay(form4_dict)