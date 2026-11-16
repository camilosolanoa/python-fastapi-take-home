CREATE TABLE coffee_records (
    id bigint PRIMARY KEY CHECK (id > 0),
    age smallint NOT NULL CHECK (age BETWEEN 18 AND 120),
    gender text NOT NULL CHECK (gender IN ('Male', 'Female', 'Other')),
    country text NOT NULL CHECK (length(country) BETWEEN 1 AND 100 AND country = btrim(country)),
    coffee_intake numeric NOT NULL CHECK (coffee_intake BETWEEN 0 AND 30),
    caffeine_mg numeric NOT NULL CHECK (caffeine_mg BETWEEN 0 AND 5000),
    sleep_hours numeric NOT NULL CHECK (sleep_hours BETWEEN 0 AND 24),
    sleep_quality text NOT NULL CHECK (sleep_quality IN ('Poor', 'Fair', 'Good', 'Excellent')),
    bmi numeric NOT NULL CHECK (bmi BETWEEN 10 AND 100),
    heart_rate smallint NOT NULL CHECK (heart_rate BETWEEN 30 AND 250),
    stress_level text NOT NULL CHECK (stress_level IN ('Low', 'Medium', 'High')),
    physical_activity_hours numeric NOT NULL CHECK (physical_activity_hours BETWEEN 0 AND 168),
    health_issues text NOT NULL CHECK (health_issues IN ('None', 'Mild', 'Moderate', 'Severe')),
    occupation text NOT NULL CHECK (occupation IN ('Office', 'Healthcare', 'Service', 'Student', 'Other')),
    smoking boolean NOT NULL,
    alcohol_consumption boolean NOT NULL
);

-- Country equality followed by ID cursor/order; add other indexes from measured workloads.
CREATE INDEX coffee_records_country_id_idx ON coffee_records (country, id);
