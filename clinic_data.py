import pandas as pd
import io
from typing import Optional, List, Dict, Tuple

class ClinicDataManager:
    def __init__(self):
        """Manages clinic locations and provider data."""
        self.locations_df = pd.DataFrame()
        self.providers_df = pd.DataFrame()
        self.load_data_from_excel()

    def load_data_from_excel(self, file_path="hillside_clinic_data.xlsx"):
        """Loads all data from the Excel file sheets upon initialization."""
        try:
            excel_data = pd.read_excel(file_path, sheet_name=None)

            if 'Clinic Locations' in excel_data:
                self.locations_df = excel_data['Clinic Locations']
                self.locations_df.columns = [col.strip() for col in self.locations_df.columns]
                print(f"✅ Successfully loaded {len(self.locations_df)} clinic locations.")

            if 'Providers' in excel_data:
                self.providers_df = excel_data['Providers']
                self.providers_df.columns = [col.strip() for col in self.providers_df.columns]
                print(f"✅ Successfully loaded {len(self.providers_df)} providers.")

        except FileNotFoundError:
            print(f"⚠️ Warning: '{file_path}' not found. The application will run without pre-loaded clinic data.")
        except Exception as e:
            print(f"💥 Error loading data from Excel file: {e}")

    def find_clinic_address(self, location_key: str) -> Optional[str]:
        """Finds the full address for a given location key (case-insensitive)."""
        if self.locations_df.empty or not location_key:
            return None

        location_key_lower = location_key.strip().lower()
        match = self.locations_df[self.locations_df['office_locations'].str.strip().str.lower() == location_key_lower]

        if not match.empty:
            return str(match.iloc[0]['Address'])
        return None

    def get_all_locations(self) -> List[Tuple[str, str]]:
        """Gets all clinic locations as (name, address) tuples."""
        if self.locations_df.empty:
            return []
        return [(row['office_locations'], row['Address']) for index, row in self.locations_df.iterrows()]

    def get_all_providers(self) -> List[Dict]:
        """Gets all provider information."""
        if self.providers_df.empty:
            return []
        return self.providers_df.to_dict('records')

    def find_providers_by_location(self, location: str) -> List[Dict]:
        """Finds providers available at a specific location (requires 'location' column in Providers sheet)."""
        if self.providers_df.empty or 'location' not in self.providers_df.columns:
            return []

        matching_providers = self.providers_df[self.providers_df['location'].str.lower() == location.lower()]
        return matching_providers.to_dict('records')

    def load_clinic_data_from_csv(self, csv_content: str) -> bool:
        """Updates clinic locations from CSV content (e.g., from an admin upload)."""
        try:
            self.locations_df = pd.read_csv(io.StringIO(csv_content))
            self.locations_df.columns = [col.strip() for col in self.locations_df.columns]
            print(f"✅ Admin uploaded and updated {len(self.locations_df)} clinic locations.")
            return True
        except Exception as e:
            print(f"❌ Error loading clinic data from admin upload: {e}")
            return False

    def load_provider_data_from_csv(self, csv_content: str) -> bool:
        """Updates providers from CSV content (e.g., from an admin upload)."""
        try:
            self.providers_df = pd.read_csv(io.StringIO(csv_content))
            self.providers_df.columns = [col.strip() for col in self.providers_df.columns]
            print(f"✅ Admin uploaded and updated {len(self.providers_df)} providers.")
            return True
        except Exception as e:
            print(f"❌ Error loading provider data from admin upload: {e}")
            return False

# Create a single instance to be used throughout the application
clinic_manager = ClinicDataManager()