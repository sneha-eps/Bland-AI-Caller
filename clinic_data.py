import pandas as pd
import io
import csv
from typing import Dict, List, Optional, Tuple
import re

class ClinicDataManager:
    """Manages clinic locations and provider data"""
    
    def __init__(self):
        self.clinic_locations = {}  # Maps clinic name to full address
        self.providers = {}  # Maps provider info
        self.location_aliases = {}  # Maps variations/aliases to standard names
        
    def load_clinic_data_from_csv(self, csv_content: str) -> bool:
        """Load clinic location data from CSV content"""
        try:
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            
            for row in csv_reader:
                office_name = row.get('office_location', '').strip()
                address = row.get('Address', '').strip()
                
                if office_name and address:
                    self.clinic_locations[office_name] = address
                    
                    # Create aliases for easier matching
                    self._create_location_aliases(office_name)
                    
            print(f"✅ Loaded {len(self.clinic_locations)} clinic locations")
            return True
            
        except Exception as e:
            print(f"❌ Error loading clinic data: {str(e)}")
            return False
            
    def load_provider_data_from_csv(self, csv_content: str) -> bool:
        """Load provider data from CSV content (when second sheet is provided)"""
        try:
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            
            for row in csv_reader:
                # Assuming provider CSV has columns like: provider_name, specialty, location, etc.
                provider_name = row.get('provider_name', '').strip()
                if provider_name:
                    self.providers[provider_name] = dict(row)
                    
            print(f"✅ Loaded {len(self.providers)} providers")
            return True
            
        except Exception as e:
            print(f"❌ Error loading provider data: {str(e)}")
            return False
    
    def _create_location_aliases(self, office_name: str):
        """Create various aliases for location matching"""
        # Store the exact name
        self.location_aliases[office_name.lower()] = office_name
        
        # Extract city/area names for partial matching
        if "Primary Care" in office_name:
            # Extract the location part after "Hillside Primary Care"
            location_part = office_name.replace("Hillside Primary Care", "").strip()
            if location_part:
                self.location_aliases[location_part.lower()] = office_name
                # Also handle comma-separated parts
                if "," in location_part:
                    parts = [part.strip() for part in location_part.split(",")]
                    for part in parts:
                        if part:
                            self.location_aliases[part.lower()] = office_name
    
    def find_clinic_address(self, location_input: str) -> Optional[str]:
        """Find the full address for a given location input (foreign key lookup)"""
        if not location_input:
            return None
            
        location_lower = location_input.lower().strip()
        
        # Direct match with aliases (foreign key lookup)
        if location_lower in self.location_aliases:
            clinic_name = self.location_aliases[location_lower]
            address = self.clinic_locations.get(clinic_name)
            print(f"🔗 Foreign Key FOUND: '{location_input}' -> '{clinic_name}' -> '{address}'")
            return address
        
        # Fuzzy matching - check if input contains any known location
        for alias, clinic_name in self.location_aliases.items():
            if alias in location_lower or location_lower in alias:
                address = self.clinic_locations.get(clinic_name)
                print(f"🔗 Foreign Key FUZZY MATCH: '{location_input}' -> '{alias}' -> '{clinic_name}' -> '{address}'")
                return address
                
        # Last resort - partial matching with clinic names
        for clinic_name, address in self.clinic_locations.items():
            if location_input.lower() in clinic_name.lower():
                print(f"🔗 Foreign Key PARTIAL MATCH: '{location_input}' -> '{clinic_name}' -> '{address}'")
                return address
        
        print(f"❌ Foreign Key NOT FOUND: '{location_input}' not found in clinic locations database")
        print(f"   Available aliases: {list(self.location_aliases.keys())}")
        return None
    
    def get_all_locations(self) -> List[Tuple[str, str]]:
        """Get all clinic locations as (name, address) tuples"""
        return [(name, address) for name, address in self.clinic_locations.items()]
    
    def get_all_providers(self) -> List[Dict]:
        """Get all provider information"""
        return list(self.providers.values())
    
    def find_providers_by_location(self, location: str) -> List[Dict]:
        """Find providers available at a specific location"""
        # This would need provider data with location information
        matching_providers = []
        for provider_data in self.providers.values():
            if 'location' in provider_data and location.lower() in provider_data['location'].lower():
                matching_providers.append(provider_data)
        return matching_providers

# Global instance
clinic_manager = ClinicDataManager()

# Initialize with the provided data
CLINIC_DATA_CSV = '''office_location,Address
Hillside Primary Care Live Oak,"12881 I35, Live Oak, TX 78233"
Hillside Primary Care Schertz,"17766 Verde Pkwy Suite 200, Schertz, TX 78154"
Hillside Primary Care Cibolo,"232 Brite Rd #117, Cibolo, TX 78108"
Hillside Primary Care Universal City,"2009 Pat Booker Road, Universal City, TX 78148"
Hillside Primary Care Windcrest,"5253-2 Walzem Rd, Windcrest, TX 78218"
Hillside Primary Care Stone Oak,"26081 Bulverde Rd, San Antonio, TX 78261"
Hillside Primary Care Castle Hills,"1009,NW Loop 410, Castle Hills, TX 78216"
Hillside Primary Care Northwest San Antonio,"4926 Golden Quail Suite 104, San Antonio, TX 78240"
Hillside Primary Care Southside,"3710 Roosevelt Ave, San Antonio, TX 78214"
"Hillside Primary Care Culebra Rd, San Antonio","1923 Culebra Road, San Antonio, TX 78201"
"Hillside Primary Care Westover Hills, San Antonio","10423 State Hwy 151, Suite 105, San Antonio, TX 78251"
Hillside Primary Care Leon Valley,"6430 Bandera Road, Suite 98, San Antonio, TX 78238"
Hillside Primary Care Kerrville,"1414 Sidney Baker St, Kerrville, TX 78028"
Hillside Primary Care Seguin,"519 N King St # 101, Seguin, TX 78155"
Hillside Primary Care New Braunfels,"741 Generation Dr. Suite 210 New Braunfels, TX, 78130"
Hillside Primary Care Kyle,"1300 Dacy Ln #110, Kyle, TX 78640"
Hillside Primary Care Austin,"11671 Jollyville Rd Ste 102, Austin, TX 78759"
Hillside Primary Care Killeen,"2201 S W S Young Dr STE 111-B, Killeen, TX 76543"
Hllside Primary Care El Paso,"840 E Redd Rd, El Paso, TX,79912"'''

# Load the clinic data on module import
clinic_manager.load_clinic_data_from_csv(CLINIC_DATA_CSV)
