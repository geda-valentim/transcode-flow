"""
Performance benchmarks for Transcode Flow.
Measures response times and throughput for critical operations.
"""
import time
import statistics
from typing import List, Dict
import psutil
import os


class PerformanceBenchmark:
    """Base class for performance benchmarking."""

    def __init__(self, name: str):
        self.name = name
        self.results: List[float] = []
        self.start_memory = 0
        self.end_memory = 0

    def measure(self, func, *args, **kwargs):
        """Measure execution time and memory usage of a function."""
        process = psutil.Process(os.getpid())
        self.start_memory = process.memory_info().rss / 1024 / 1024  # MB

        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()

        self.end_memory = process.memory_info().rss / 1024 / 1024  # MB
        execution_time = (end_time - start_time) * 1000  # Convert to ms
        self.results.append(execution_time)

        return result, execution_time

    def run_iterations(self, func, iterations: int = 100, *args, **kwargs):
        """Run function multiple times and collect stats."""
        print(f"\nBenchmark: {self.name}")
        print(f"Running {iterations} iterations...")

        for i in range(iterations):
            if i % 10 == 0:
                print(f"  Progress: {i}/{iterations}", end="\r")
            _, _ = self.measure(func, *args, **kwargs)

        print(f"  Progress: {iterations}/{iterations} ✓")
        self.print_stats()

    def print_stats(self):
        """Print benchmark statistics."""
        if not self.results:
            print("  No results to display")
            return

        avg_time = statistics.mean(self.results)
        median_time = statistics.median(self.results)
        min_time = min(self.results)
        max_time = max(self.results)
        std_dev = statistics.stdev(self.results) if len(self.results) > 1 else 0
        memory_delta = self.end_memory - self.start_memory

        print("\n  Results:")
        print(f"    Average:  {avg_time:.2f}ms")
        print(f"    Median:   {median_time:.2f}ms")
        print(f"    Min:      {min_time:.2f}ms")
        print(f"    Max:      {max_time:.2f}ms")
        print(f"    Std Dev:  {std_dev:.2f}ms")
        print(f"    Memory Δ: {memory_delta:.2f}MB")
        print(f"    Throughput: {1000/avg_time:.2f} ops/sec")


def benchmark_api_key_generation():
    """Benchmark API key generation."""
    from app.api.v1.endpoints.api_keys import generate_api_key

    def generate_key():
        return generate_api_key()

    bench = PerformanceBenchmark("API Key Generation")
    bench.run_iterations(generate_key, iterations=1000)


def benchmark_token_generation():
    """Benchmark JWT token generation."""
    from app.services.streaming_tokens import StreamingTokenService

    service = StreamingTokenService(secret_key="test_secret", redis_client=None)

    def generate_token():
        return service.generate_token(
            job_id="test-job",
            api_key_prefix="tfk_test",
            expires_in_seconds=3600,
        )

    bench = PerformanceBenchmark("JWT Token Generation")
    bench.run_iterations(generate_token, iterations=1000)


def benchmark_token_validation():
    """Benchmark JWT token validation."""
    from app.services.streaming_tokens import StreamingTokenService

    service = StreamingTokenService(secret_key="test_secret", redis_client=None)
    token = service.generate_token(
        job_id="test-job",
        api_key_prefix="tfk_test",
        expires_in_seconds=3600,
    )

    def validate_token():
        return service.validate_token(token)

    bench = PerformanceBenchmark("JWT Token Validation")
    bench.run_iterations(validate_token, iterations=1000)


def benchmark_database_queries():
    """Benchmark common database queries."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.api_key import APIKey
    import hashlib

    # Use in-memory SQLite for benchmarking
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)

    # Create tables
    from app.models.api_key import Base
    Base.metadata.create_all(bind=engine)

    # Seed data
    session = SessionLocal()
    for i in range(100):
        api_key = APIKey(
            key_hash=hashlib.sha256(f"key_{i}".encode()).hexdigest(),
            key_prefix=f"tfk_test_{i}",
            name=f"Test Key {i}",
            is_active=True,
            permissions={},
            scopes=[],
        )
        session.add(api_key)
    session.commit()

    def query_by_id():
        return session.query(APIKey).filter(APIKey.id == 50).first()

    def query_by_prefix():
        return session.query(APIKey).filter(APIKey.key_prefix == "tfk_test_50").first()

    def query_all_active():
        return session.query(APIKey).filter(APIKey.is_active == True).all()

    bench1 = PerformanceBenchmark("DB Query: By ID")
    bench1.run_iterations(query_by_id, iterations=100)

    bench2 = PerformanceBenchmark("DB Query: By Prefix")
    bench2.run_iterations(query_by_prefix, iterations=100)

    bench3 = PerformanceBenchmark("DB Query: All Active")
    bench3.run_iterations(query_all_active, iterations=100)

    session.close()


def benchmark_json_serialization():
    """Benchmark JSON serialization of large objects."""
    import json

    # Create large job output structure
    large_job_output = {
        "hls": {
            f"{res}p": {
                "manifest": f"jobs/test/hls/{res}p/manifest.m3u8",
                "segments": [f"jobs/test/hls/{res}p/segment_{i}.ts" for i in range(100)],
            }
            for res in ["1080", "720", "480", "360"]
        },
        "mp4": {
            f"{res}p": f"jobs/test/mp4/{res}p/video.mp4"
            for res in ["1080", "720", "480"]
        },
    }

    def serialize():
        return json.dumps(large_job_output)

    def deserialize(data):
        return json.loads(data)

    serialized_data = json.dumps(large_job_output)

    bench1 = PerformanceBenchmark("JSON Serialization (Large Object)")
    bench1.run_iterations(serialize, iterations=1000)

    bench2 = PerformanceBenchmark("JSON Deserialization (Large Object)")
    bench2.run_iterations(deserialize, serialized_data, iterations=1000)


def run_all_benchmarks():
    """Run all performance benchmarks."""
    print("=" * 60)
    print("  TRANSCODE FLOW PERFORMANCE BENCHMARKS")
    print("=" * 60)

    benchmark_api_key_generation()
    benchmark_token_generation()
    benchmark_token_validation()
    benchmark_database_queries()
    benchmark_json_serialization()

    print("\n" + "=" * 60)
    print("  BENCHMARKS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    run_all_benchmarks()
