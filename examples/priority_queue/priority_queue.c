#include <stdlib.h>

#include "priority_queue.h"

unsigned get_parent(unsigned const element_index);
unsigned get_first_child(unsigned const element_index);

inline unsigned get_parent(unsigned const element_index)
{
    return (element_index - 1)/2;
}

inline unsigned get_first_child(unsigned const element_index)
{
    return 2 * element_index + 1;
}

struct PriorityQueue* new_priority_queue(unsigned const heap_size)
{
    struct PriorityQueue* heap;
    if ((heap = malloc(sizeof(*heap))) == NULL) {
        return NULL;
    }
    if ((heap->array = malloc(heap_size * sizeof(*(heap->array)))) == NULL) {
        free(heap);
        return NULL;
    }
    heap->size = 0;
    heap->max_size = heap_size;
    return heap;
}

int priority_queue_push(struct PriorityQueue* const heap,
                        const HeapElement element)
{
    if (heap->size >= heap->max_size) {
        return 1;
    }
    unsigned element_index = heap->size;
    for (unsigned parent_index; element_index > 0; element_index = parent_index) {
        parent_index = get_parent(element_index);
        HeapElement parent = heap->array[parent_index];
        if (element >= parent) {
            break;
        }
        heap->array[element_index] = parent;
    }
    heap->array[element_index] = element;
    heap->size++;
    return 0;
}

HeapElement* find_priority_queue_min(const struct PriorityQueue* heap)
{
    if (heap->size == 0) {
        return NULL;
    }
    return &(heap->array[0]);
}

int delete_priority_queue_min(struct PriorityQueue* const heap)
{
    if (heap->size == 0) {
        return 1;
    }
    HeapElement element = heap->array[--(heap->size)];
    unsigned element_index = 0;
    for (unsigned first_child = get_first_child(element_index);
         first_child < heap->size;
         first_child = get_first_child(element_index))
    {
        unsigned lowest_child;
        unsigned second_child = first_child + 1;
        if ((second_child < heap->size) && (heap->array[first_child] >
                                          heap->array[second_child])){
            lowest_child = second_child;
        } else {
            lowest_child = first_child;
        }
        if (element <= heap->array[lowest_child]) {
            break;
        }
        heap->array[element_index] = heap->array[lowest_child];
        element_index = lowest_child;
    }
    heap->array[element_index] = element;

    return 0;
}

HeapElement priority_queue_pop(struct PriorityQueue* queue)
{
    HeapElement element = *find_priority_queue_min(queue); // Segmentation Fault if empty
    delete_priority_queue_min(queue);
    return element;
}

void free_priority_queue(struct PriorityQueue* const heap)
{
    if (heap == NULL) {
        return;
    }
    free(heap->array);
    free(heap);
}
